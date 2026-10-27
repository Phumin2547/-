"""ตรวจสอบข้อมูลที่ดึงจาก Shipnity และหาสาเหตุของส่วนต่างเมื่อเทียบกับ Express (ไม่มี UI)

  bridge(all_lines, lines)            สะพานจำนวน: ดึงได้ทั้งหมด → ตัดยกเลิก → ที่นับจริง
  quality_checks(lines)               ตรวจคุณภาพข้อมูลที่ดึงมา (ซ้ำ / ยอดผิดปกติ / กลุ่มผสมหลายขนส่ง)
  reconcile(...)                      รายใบกำกับ: ส่วนต่าง + สาเหตุ + หลักฐาน + ความมั่นใจของการจับคู่
  variance_bridge(rec, ...)           สะพานยอดขาย Shipnity → Express แยกตามสาเหตุ
"""

import re

import pandas as pd

from backend import shipnity_promo as sp

SHIPPING_CODE = "4230"       # ค่าจัดส่งใน CSV (ไม่เทียบจำนวน)
TOL = 0.005

CONF = {"code": "สูง (รหัสลูกค้า)", "exact": "สูง (ยอดตรงเป๊ะ)", "by_order": "ต่ำ (ยอดใกล้เคียง)"}


def _orders(df):
    return df.drop_duplicates("เลขที่ออเดอร์")


# =========================================================
# ช่วงที่ 1: ตรวจข้อมูลที่ดึงมา
# =========================================================

def bridge(all_lines: pd.DataFrame, lines: pd.DataFrame) -> pd.DataFrame:
    """ตารางสะพาน: ตัวเลขเปลี่ยนไปในแต่ละขั้นเท่าไร"""

    rows = []

    def add(step, o, l, v, note=""):
        rows.append({"ขั้นตอน": step, "ออเดอร์": o, "บรรทัด": l, "ยอดขาย": round(float(v), 2), "หมายเหตุ": note})

    src = all_lines if all_lines is not None else lines

    so = _orders(src)
    add("ดึงจาก Shipnity ได้ทั้งหมด", len(so), len(src), so["ยอดขาย"].sum(), "ตรงกับไฟล์ export ของ Shipnity")

    if "ยกเลิก" in src.columns:
        c = src[src["ยกเลิก"]]
        co = _orders(c)
        add("− ตัดออเดอร์ยกเลิก", -len(co), -len(c), -co["ยอดขาย"].sum(), "หมายเหตุยกเลิก/สินค้าหมด")

        kept = src[~src["ยกเลิก"]]
        ko = _orders(kept)
        add("= ที่นับในหน้านี้", len(ko), len(kept), ko["ยอดขาย"].sum())

    lo = _orders(lines)

    tax = lo[lo["รหัสลูกค้า"].astype(str).str.startswith(sp.TAX_CODE_PREFIX)]
    add("ในนั้น: ขอใบกำกับภาษี (แยกเป็นบิลของตัวเอง)", len(tax), int(lines["เลขที่ออเดอร์"].isin(tax["เลขที่ออเดอร์"]).sum()), tax["ยอดขาย"].sum())

    return pd.DataFrame(rows)


def quality_checks(lines: pd.DataFrame) -> list:
    """คืน [(ระดับ, ข้อความ)] ระดับ = ok / warn"""

    out = []

    dup = lines.duplicated(subset=[
        "เลขที่ออเดอร์", "รหัสสินค้า (ดิบ)", "จำนวน", "ราคา", "มูลค่าสุทธิ"
    ], keep=False)

    # สินค้าชิ้นเดียวกันซ้ำในออเดอร์เดียวกันเป็นเรื่องปกติ (ลงสองบรรทัด) จึงนับเป็นข้อสังเกตเท่านั้น
    if dup.any():
        n = lines.loc[dup, "เลขที่ออเดอร์"].nunique()
        out.append(("info", f"{n:,} ออเดอร์มีบรรทัดสินค้าเหมือนกันทุกช่องซ้ำกัน (ปกติถ้าลงสินค้าเดียวกันแยกบรรทัด)"))

    o = _orders(lines)

    bad = o[o["ยอดขาย"] <= 0]
    out.append(("warn", f"{len(bad):,} ออเดอร์ยอดขาย ≤ 0: " + ", ".join(bad["เลขที่ออเดอร์"].head(8)))
               if len(bad) else ("ok", "ไม่มีออเดอร์ยอดขาย ≤ 0"))

    neg = lines[(lines["จำนวน"] <= 0)]
    out.append(("warn", f"{len(neg):,} บรรทัดจำนวน ≤ 0") if len(neg) else ("ok", "ทุกบรรทัดมีจำนวนมากกว่า 0"))

    # ยอดขายออเดอร์ vs ผลรวมมูลค่าสุทธิของบรรทัด (+ ค่าส่ง) — ต่างมากอาจเป็นส่วนลดระดับออเดอร์
    s = lines.groupby("เลขที่ออเดอร์").agg(net=("มูลค่าสุทธิ", "sum"), ship=("ค่าส่ง", "first"), sale=("ยอดขาย", "first"))
    gap = s[(s["net"] + s["ship"] - s["sale"]).abs() > 1.0]
    out.append(("info", f"{len(gap):,} ออเดอร์ที่ผลรวมบรรทัด + ค่าส่ง ไม่เท่ายอดขายของออเดอร์ (เกิน 1 บาท)")
               if len(gap) else ("ok", "ผลรวมบรรทัดตรงกับยอดขายของทุกออเดอร์"))

    # กลุ่มที่ปนหลายขนส่ง
    mix = (
        o.groupby(["ช่องทางการเปิดบิล", "รหัสลูกค้า"])["ขนส่ง"].nunique()
    )
    mix = mix[mix > 1]
    if len(mix):
        out.append(("info", "กลุ่มที่รวมหลายขนส่ง (ตัวเลขรายขนส่งในกลุ่มนี้ไม่ละเอียด): "
                    + ", ".join(f"{c} ({n} ขนส่ง)" for (_, c), n in mix.items())))

    unk = sorted({c for c in o["รหัสลูกค้า"] if str(c).startswith("ไม่ทราบ")})
    out.append(("warn", "ขนส่งที่ยังไม่มีรหัสลูกค้า: " + ", ".join(unk)) if unk else ("ok", "ทุกขนส่งมีรหัสลูกค้า"))

    return out


# =========================================================
# ช่วงที่ 2: หาสาเหตุของส่วนต่างเทียบกับ Express
# =========================================================

def _shipnity_qty(g: pd.DataFrame, known) -> dict:

    d = {}

    for code, q in zip(g["รหัสสินค้า (ดิบ)"], g["จำนวน"]):
        k = sp.norm_code(sp.strip_prefix(code, known))
        if k == SHIPPING_CODE:
            continue
        d[k] = d.get(k, 0) + int(round(float(q)))

    return d


def reconcile(lines, csv_orders, csv_items, restored=None, methods=None, known=None) -> pd.DataFrame:
    """1 แถว = 1 ใบกำกับ (CSV) หรือ 1 บล็อกที่ไม่มีใบกำกับ พร้อมสาเหตุและหลักฐาน

    lines   ผลหลัง assign_invoices + restore_cancelled (มีคอลัมน์เลขที่ใบกำกับ)
    """

    restored = restored if restored is not None else pd.DataFrame(columns=["เลขที่ออเดอร์", "ยอดขาย", "เลขที่ใบกำกับ"])
    methods = methods or {}
    known = known or set()

    rows = []

    inv_lines = lines[lines["เลขที่ใบกำกับ"].astype(str) != ""]

    csv_orders = csv_orders.drop_duplicates("เลขที่ใบกำกับสินค้า")

    for _, iv in csv_orders.iterrows():

        inv = str(iv["เลขที่ใบกำกับสินค้า"])
        csv_amt = float(iv["ยอดขาย"])
        g = inv_lines[inv_lines["เลขที่ใบกำกับ"].astype(str) == inv]

        if g.empty:
            rows.append({
                "เลขที่ใบกำกับ": inv, "ช่องทาง": iv["ประเภทช่องทาง"], "รหัสลูกค้า": "-", "ออเดอร์": 0,
                "ยอด CSV": csv_amt, "ยอด Shipnity": 0.0, "ส่วนต่าง": -csv_amt,
                "ความมั่นใจการจับคู่": "-", "สาเหตุ": "มีเฉพาะใน Express",
                "หลักฐาน": "ไม่มีบล็อกใน Shipnity ที่จับคู่กับใบนี้", "กลุ่มสาเหตุ": "บิลฝั่งเดียว",
            })
            continue

        o = _orders(g)
        ship_amt = round(float(o["ยอดขาย"].sum()), 2)
        diff = round(ship_amt - csv_amt, 2)

        ch, code = g["ช่องทางการเปิดบิล"].iloc[0], g["รหัสลูกค้า"].iloc[0]
        conf = CONF.get(methods.get((ch, code)), "-")

        rest = restored[restored["เลขที่ใบกำกับ"].astype(str) == inv]
        rest_amt = round(float(rest["ยอดขาย"].sum()), 2) if len(rest) else 0.0

        # เทียบจำนวนสินค้า
        ci = csv_items[csv_items["เลขที่ใบกำกับ"].astype(str) == inv]
        cq = {}
        for c, q in zip(ci["รหัสสินค้า"], ci["จำนวน CSV"]):
            if str(c) != SHIPPING_CODE:
                cq[str(c)] = cq.get(str(c), 0) + int(q)

        sq = _shipnity_qty(g, known)

        deltas = {k: sq.get(k, 0) - cq.get(k, 0) for k in set(sq) | set(cq) if sq.get(k, 0) != cq.get(k, 0)}

        if abs(diff) < TOL:
            if len(rest):
                reason, grp = "ตรง (หลังคืนออเดอร์ที่ยกเลิกแต่ลงบิลแล้ว)", "ยกเลิกหลังลงบิล"
                ev = "คืนออเดอร์: " + ", ".join(f"{r.เลขที่ออเดอร์} ({r.ยอดขาย:,.2f})" for r in rest.itertuples())
            else:
                reason, grp, ev = "ตรง", "ตรง", ""
        elif not ci.shape[0]:
            reason, grp = "ยอดไม่ตรง (ไม่มีรายการสินค้าใน CSV ให้เทียบ)", "ไม่ทราบสาเหตุ"
            ev = "อัป CSV ที่มีรายการสินค้าเพื่อให้เทียบได้"
        elif not deltas:
            reason, grp = "จำนวนสินค้าตรงกัน แต่ยอดต่าง → ส่วนลด/ราคา/ค่าส่งไม่เท่ากัน", "ส่วนลด/ราคา"
            ev = f"สินค้าเท่ากันทุกรหัส · Shipnity {ship_amt:,.2f} · Express {csv_amt:,.2f}"
        else:
            reason, grp = "สินค้าไม่ตรงกัน", "สินค้าต่างกัน"
            ev = "; ".join(f"{k} {v:+d}" for k, v in sorted(deltas.items())[:8]) + "  (Shipnity − Express)"

        rows.append({
            "เลขที่ใบกำกับ": inv, "ช่องทาง": iv["ประเภทช่องทาง"], "รหัสลูกค้า": code, "ออเดอร์": len(o),
            "ยอด CSV": csv_amt, "ยอด Shipnity": ship_amt, "ส่วนต่าง": diff,
            "ความมั่นใจการจับคู่": conf, "สาเหตุ": reason, "หลักฐาน": ev, "กลุ่มสาเหตุ": grp,
            "_คืน": rest_amt,
        })

    # บล็อกของ Shipnity ที่ไม่มีใบกำกับ
    no_inv = lines[lines["เลขที่ใบกำกับ"].astype(str) == ""]

    for (ch, code), g in no_inv.groupby(["ช่องทางการเปิดบิล", "รหัสลูกค้า"]):
        o = _orders(g)
        amt = round(float(o["ยอดขาย"].sum()), 2)
        rows.append({
            "เลขที่ใบกำกับ": "-", "ช่องทาง": ch, "รหัสลูกค้า": code, "ออเดอร์": len(o),
            "ยอด CSV": 0.0, "ยอด Shipnity": amt, "ส่วนต่าง": amt,
            "ความมั่นใจการจับคู่": "-", "สาเหตุ": "มีเฉพาะใน Shipnity",
            "หลักฐาน": "ไม่มีใบกำกับใน CSV ที่จับคู่กับกลุ่มนี้", "กลุ่มสาเหตุ": "บิลฝั่งเดียว", "_คืน": 0.0,
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df["_abs"] = df["ส่วนต่าง"].abs()

    return df.sort_values("_abs", ascending=False).drop(columns="_abs").reset_index(drop=True)


def variance_bridge(rec: pd.DataFrame, shipnity_before_restore: float):
    """สะพานยอดขาย: Shipnity → Express แยกตามกลุ่มสาเหตุ + % ที่อธิบายได้

    คืน (ตาราง, สรุป dict)
    """

    if rec.empty:
        return pd.DataFrame(), {"total_diff": 0.0, "explained_pct": 100.0, "unknown": 0.0}

    restored = float(rec["_คืน"].sum()) if "_คืน" in rec else 0.0

    ship_total = float(rec["ยอด Shipnity"].sum())
    csv_total = float(rec["ยอด CSV"].sum())
    total_diff = round(ship_total - csv_total, 2)

    g = rec[rec["ส่วนต่าง"].abs() >= TOL].groupby("กลุ่มสาเหตุ")["ส่วนต่าง"].agg(["size", "sum"])

    rows = [
        {"รายการ": "ยอดขาย Shipnity (หลังตัดยกเลิก)", "ใบกำกับ": None, "ยอด": round(shipnity_before_restore, 2)},
        {"รายการ": "+ คืนออเดอร์ที่ยกเลิกแต่ Express ลงบิลแล้ว", "ใบกำกับ": int((rec.get("_คืน", 0) > 0).sum()), "ยอด": round(restored, 2)},
        {"รายการ": "= ยอด Shipnity ที่ใช้เทียบ", "ใบกำกับ": None, "ยอด": round(ship_total, 2)},
        {"รายการ": "ยอดขาย Express (CSV)", "ใบกำกับ": None, "ยอด": round(csv_total, 2)},
        {"รายการ": "ส่วนต่างรวม (Shipnity − Express)", "ใบกำกับ": None, "ยอด": total_diff},
    ]

    for name, r in g.iterrows():
        rows.append({"รายการ": f"   · {name}", "ใบกำกับ": int(r["size"]), "ยอด": round(float(r["sum"]), 2)})

    unknown = float(g.loc["ไม่ทราบสาเหตุ", "sum"]) if "ไม่ทราบสาเหตุ" in g.index else 0.0
    explained = 100.0 if abs(total_diff) < TOL else max(0.0, (1 - abs(unknown) / max(abs(total_diff), TOL)) * 100)

    return pd.DataFrame(rows), {"total_diff": total_diff, "explained_pct": round(explained, 1), "unknown": unknown}