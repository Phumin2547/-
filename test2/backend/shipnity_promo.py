"""รายงาน "โปรโมชั่น" ของ Shipnity (รายบรรทัดสินค้า) ดึงจาก GraphQL แล้วแปลงเป็น
   1) ตารางรายบรรทัด (lines)  2) ไฟล์ Excel แบบบล็อกเดียวกับรายงานที่ทีมเคลียร์แล้ว
   เพื่อให้ order_detail_logic ใช้ตรรกะเทียบเดิมได้ทันที

ไม่ import streamlit

สิ่งที่พบจากการเทียบไฟล์ดิบ (Data_xx) กับไฟล์ที่เคลียร์แล้ว (Shipnity โปรโมชั่น) — ข้อมูลรายบรรทัดตรงกันทุกค่า
ส่วนที่ "ทีมเติมเอง" และถูกจำลองในไฟล์นี้:
    ช่องทางการเปิดบิล   contactMethod มีคำว่า phone → Callcenter/SE นอกนั้น Online/SK
    รหัสลูกค้า (VS...)  ตามขนส่ง+วิธีชำระ (ตาราง CUSTOMER_RULES) · 1 บล็อก = 1 (ช่องทาง, รหัสลูกค้า)
    รหัสสินค้า          ตัดตัวนำหน้า N_ / X_ ออก
ส่วนที่ Shipnity ไม่มี (มาจาก Express): เลขใบกำกับ IK/WG/IE, เลข SK, วันที่ IK, RF, CN
    → จับคู่บล็อกกับใบกำกับใน CSV ด้วย assign_invoices()
ลูกค้าที่ขอใบกำกับพิเศษ (E-TAX ฯลฯ) ที่ทีมแยกบล็อกเอง ไฟล์ดิบแยกไม่ได้ จะรวมอยู่ในบล็อกตามขนส่ง
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd

from backend import shipnity_api as sn

# =========================================================
# CONFIG
# =========================================================

PROMO_TEMPLATE = str(Path(__file__).with_name("shipnity_request_promo.json"))

CH_ONLINE = "Online/SK"
CH_CALL = "Callcenter/SE"

# กฎจับช่องทางการเปิดบิล: (ฟิลด์ของ order, regex, ช่องทาง) — ไม่ตรงกฎใดเลย = Online
CHANNEL_RULES = [
    ("contactMethod", r"phone", CH_CALL),
]
DEFAULT_CHANNEL = CH_ONLINE

# รหัสลูกค้า Express ตามขนส่ง/วิธีชำระ (ตรวจจากไฟล์จริง) — เจอกฎแรกที่ตรงใช้เลย
CUSTOMER_RULES = [
    (r"speed.*cod", "VS001-01"),
    (r"speed", "VS001"),
    (r"kerry.*cod", "VS003-01"),
    (r"kerry", "VS003"),
    (r"dhl.*cod", "VS012-01"),
    (r"dhl", "VS012"),
    (r"j\s*&\s*t", "VS011"),
    (r"lazada", "VS007"),
    (r"spx|shopee|flash|express delivery", "VS006"),
]

SALES_FIELD = "shopReportPrice"       # หรือ "price"
SKIP_CANCELLED = True
# ออเดอร์ที่ Shipnity ว่ายกเลิก จะ "ตัดทิ้ง" เฉพาะที่หมายเหตุเข้าข่ายนี้ (เช่น "สินค้าหมด") ที่เหลือคงไว้
# เพราะบางออเดอร์ยกเลิกหลังลงบิล Express ไปแล้ว ทีมยังนับเป็นยอดขาย
CUT_CANCELLED_NOTE_RE = r"สินค้าหมด|ยกเลิก|cancel"
KEEP_CANCELLED = set()   # เลขออเดอร์ที่ยกเลิกใน Shipnity แต่ทีมยังลงบิลไว้ เช่น {"MO261021-xxx"}
SLACK_HOURS = 6        # หยุดดึงเมื่อทั้งหน้าเก่ากว่าวันเริ่มต้นเกินกี่ชั่วโมง (กันลำดับรายงานไม่เรียงเป๊ะ)
BACKUP_PAGES = 20      # ตอนกระโดดข้ามหน้า ถอยกลับกี่หน้า
STRIP_PREFIX_RE = re.compile(r"^[A-Za-z]{1,5}_")     # ใช้ตอนไม่มีรหัส Express ให้ตรวจ

LINE_COLUMNS = [
    "เลขที่ออเดอร์", "ช่องทางการเปิดบิล", "รหัสลูกค้า", "เลขที่ใบกำกับ", "ใบสั่งขาย", "วันที่ IK", "ขนส่ง", "ชำระ",
    "รหัสสินค้า (ดิบ)", "ชื่อรายการ", "จำนวน", "ราคา", "มูลค่าสุทธิ",
    "ค่าส่ง", "ส่วนลด", "ยอดขาย", "วันที่พิมพ์",
    "contactMethod", "createdBy", "printedBy", "หมายเหตุ", "ยกเลิก",
]


# =========================================================
# ดึงข้อมูล
# =========================================================

def _order(n):
    return (n or {}).get("order") or {}


def _printed(n):
    o = _order(n)
    return sn._to_local(o.get("printedAt") or o.get("transferredAt") or n.get("updatedAt"))


def fetch_lines(cfg, date_from, date_to, max_pages=800, progress=None, session=None):
    """ดึงบรรทัดสินค้าที่พิมพ์ระหว่างช่วงวันที่ → (lines DataFrame, info)

    ให้ Shipnity กรองวันที่เองก่อน (เหมือนหน้าเว็บ/ไฟล์ export); ถ้าเซิร์ฟเวอร์ไม่รับ จึงถอยไปไล่ดึงเอง
    """

    try:

        nodes, info = sn.fetch_server_range(
            cfg, date_from, date_to, PROMO_TEMPLATE,
            max_pages=max(max_pages, 8000), progress=progress, session=session, time_of=_printed
        )

    except sn.ShipnityError as e:

        if any(w in str(e) for w in ("ปฏิเสธการเข้าถึง", "ไม่พบไฟล์", "ไม่ใช่ JSON ที่ถูกต้อง", "วันที่สิ้นสุด")):
            raise

        nodes, info = sn.fetch_orders(
            cfg, date_from, date_to, max_pages=max_pages, progress=progress, session=session,
            template_path=PROMO_TEMPLATE, time_of=_printed, key_of=lambda n: None, raw=True,
            slack_hours=SLACK_HOURS, backup_pages=BACKUP_PAGES
        )

        info["warnings"].append(
            f"ให้ Shipnity กรองวันที่เองไม่ได้ ({str(e)[:120]}) — ใช้วิธีไล่ดึงทีละหน้าแทน อาจได้ไม่ตรงไฟล์ export"
        )

    lines = nodes_to_lines(nodes)

    if len(lines):
        keep = lines["ยกเลิก"] & ~lines["หมายเหตุ"].str.contains(CUT_CANCELLED_NOTE_RE, case=False, regex=True, na=False)
        kept_n = lines.loc[keep, "เลขที่ออเดอร์"].nunique()
        info["kept_cancelled"] = lines.loc[keep].drop_duplicates("เลขที่ออเดอร์")[
            ["เลขที่ออเดอร์", "ช่องทางการเปิดบิล", "ขนส่ง", "ยอดขาย", "วันที่พิมพ์", "หมายเหตุ"]
        ].reset_index(drop=True)
        lines.loc[keep, "ยกเลิก"] = False

        if kept_n:
            info["warnings"].append(
                f"มีออเดอร์ที่ Shipnity ระบุว่ายกเลิกแต่ไม่มีหมายเหตุยกเลิก {kept_n:,} ออเดอร์ — คงไว้ในยอด"
                f" (เหมือนที่ทีมทำ)"
            )

    info["all_lines"] = lines            # ก่อนตัดออเดอร์ยกเลิก (ไว้ตรวจเทียบกับไฟล์ที่ส่งออกจาก Shipnity)

    if len(lines) and KEEP_CANCELLED:
        lines.loc[lines["เลขที่ออเดอร์"].isin(KEEP_CANCELLED), "ยกเลิก"] = False

    cancelled = int(lines["ยกเลิก"].sum()) if len(lines) else 0

    if SKIP_CANCELLED and cancelled:
        lines = lines[~lines["ยกเลิก"]].reset_index(drop=True)
        info["warnings"].append(f"ตัดบรรทัดของออเดอร์ที่ยกเลิกแล้ว {cancelled:,} บรรทัด")

    info["kept"] = len(lines)

    return lines, info


# =========================================================
# แปลง API → lines
# =========================================================

def _s(x):
    return "" if x is None else str(x).strip()


def _channel(o):

    for field, rx, ch in CHANNEL_RULES:
        if re.search(rx, _s(o.get(field)), re.I):
            return ch

    return DEFAULT_CHANNEL


# ออเดอร์ที่ลูกค้าขอใบกำกับภาษี ทีมออกบิลแยกใบ (รหัสลูกค้าเป็นของลูกค้ารายนั้น) → แยกเป็นบล็อกของตัวเอง
TAX_NOTE_RE = r"ใบกำกับ|e-?tax"
TAX_CODE_PREFIX = "ใบกำกับภาษี:"


def customer_code(ship) -> str:
    """รหัสลูกค้า Express จากชื่อขนส่ง (เช่น "Kerry COD" → VS003-01); ไม่รู้จัก = ใช้ชื่อขนส่งเป็นกลุ่มเอง"""

    t = _s(ship)

    for rx, code in CUSTOMER_RULES:
        if re.search(rx, t, re.I):
            return code

    return "ไม่ทราบ:" + t


def _pay(ship) -> str:
    """วิธีชำระ อ่านจากชื่อขนส่ง (ชื่อขนส่งของ Shipnity มี COD / โอนเงิน ต่อท้ายอยู่แล้ว)"""

    t = _s(ship).lower()

    return "COD" if "cod" in t else "โอนเงิน" if "โอน" in t else "-"


def nodes_to_lines(nodes) -> pd.DataFrame:

    rows = []

    for n in nodes:

        o = _order(n)

        sales = o.get(SALES_FIELD)
        sales = o.get("price") if sales is None else sales

        ship = _s(o.get("shippingType"))

        rows.append({
            "เลขที่ออเดอร์": _s(o.get("invoiceNumber")),
            "ช่องทางการเปิดบิล": _channel(o),
            "รหัสลูกค้า": (
                TAX_CODE_PREFIX + _s(o.get("invoiceNumber"))
                if re.search(TAX_NOTE_RE, _s(o.get("annotation")), re.I) else customer_code(ship)
            ),
            "เลขที่ใบกำกับ": "",
            "ใบสั่งขาย": "",
            "วันที่ IK": "",
            "ขนส่ง": ship,
            "ชำระ": _pay(ship),
            "รหัสสินค้า (ดิบ)": _s((n.get("product") or {}).get("code")),
            "ชื่อรายการ": _s(n.get("name")),
            "จำนวน": sn._num(n.get("quantity")),
            "ราคา": sn._num(n.get("price")),
            "มูลค่าสุทธิ": sn._num(n.get("totalValue")),
            "ค่าส่ง": sn._num(o.get("shippingFee")),
            "ส่วนลด": sn._num(o.get("totalDiscount")),
            "ยอดขาย": sn._num(sales),
            "วันที่พิมพ์": sn._fmt_dt(o.get("printedAt")),
            "contactMethod": _s(o.get("contactMethod")),
            "createdBy": _s(o.get("createdBy")),
            "printedBy": _s(o.get("printedBy")),
            "หมายเหตุ": _s(o.get("annotation")),
            "ยกเลิก": bool(o.get("cancelled")),
        })

    return pd.DataFrame(rows, columns=LINE_COLUMNS)


# =========================================================
# รหัสสินค้า: ตัดตัวนำหน้า  N_W1M_FM18 → W1M_FM18
# =========================================================

def norm_code(x) -> str:
    """รูปแบบเทียบรหัส (ตรงกับ _inv_norm_code ของหน้ารายละเอียดออเดอร์)"""

    x = re.sub(r"[\s\xa0_]+", "_", str(x).strip()).upper()

    return x.lstrip("0") if x.isdigit() else x


def strip_prefix(code, known=None) -> str:
    """ตัดส่วนนำหน้าถึง "_" ตัวแรก

    มีรหัสจาก Express (known) → รหัสเดิมตรงกับ Express อยู่แล้วไม่ตัด; ไม่ตรง แต่ตัดแล้วตรง ให้ตัด;
                              ไม่ตรงทั้งคู่ ตัดเมื่อส่วนนำหน้าเป็นตัวอักษรล้วน
    ไม่มีรหัส Express          → ตัดเมื่อส่วนนำหน้าเป็นตัวอักษรล้วนสั้น ๆ (เช่น N_) เท่านั้น
    """

    raw = _s(code)

    if "_" not in raw:
        return raw

    rest = raw.split("_", 1)[1]

    if known:

        if norm_code(raw) in known:
            return raw

        if norm_code(rest) in known:
            return rest

    return rest if STRIP_PREFIX_RE.match(raw) else raw


def apply_codes(lines: pd.DataFrame, known=None) -> pd.DataFrame:

    out = lines.copy()
    out["รหัสสินค้า"] = out["รหัสสินค้า (ดิบ)"].map(lambda c: strip_prefix(c, known))

    return out


# =========================================================
# จับคู่บล็อก ↔ ใบกำกับใน CSV Express (Shipnity ไม่มีเลข IK/WG/IE)
# =========================================================

def blocks_of(lines: pd.DataFrame) -> pd.DataFrame:
    """1 แถว = 1 บล็อก (ช่องทาง, รหัสลูกค้า) พร้อมยอดขายรวมต่อออเดอร์"""

    orders = lines.drop_duplicates("เลขที่ออเดอร์")

    b = (
        orders.groupby(["ช่องทางการเปิดบิล", "รหัสลูกค้า"], sort=True)
        .agg(ออเดอร์=("เลขที่ออเดอร์", "nunique"), ยอดขาย=("ยอดขาย", "sum"))
        .reset_index()
    )

    b["ยอดขาย"] = b["ยอดขาย"].round(2)

    return b


def _has_code(text, code) -> bool:
    return bool(re.search(rf"(?<![\w-]){re.escape(str(code))}(?![\w-])", str(text), re.I))


def assign_invoices(lines: pd.DataFrame, csv_orders: pd.DataFrame):
    """เติมข้อมูลที่ Shipnity ไม่มี (เลขใบกำกับ IK/WG/IE, ใบสั่งขาย SK, วันที่ IK) จาก CSV Express
    โดยจับคู่ "บล็อก" (ช่องทาง + รหัสลูกค้า) กับใบกำกับ ในแต่ละช่องทาง:

      0) ข้อความของใบกำกับใน CSV มีรหัสลูกค้า (VS001 ฯลฯ) ตรงกับบล็อก → จับคู่ด้วยรหัสก่อน (แม่นที่สุด)
      1) ยอดขายเท่ากันเป๊ะ
      2) ที่เหลือ → จับคู่ตามยอดที่ใกล้กันที่สุด (จำนวนไม่เท่ากันจับเฉพาะคู่ที่ยอดต่างไม่เกิน 25%) (ยอดต่างจะขึ้นเป็น "ยอดไม่ตรง")
      3) จับคู่ไม่ได้ → บล็อกไม่มีเลขใบกำกับ / ใบกำกับไม่มีใน Shipnity
    คืน (lines ที่เติมแล้ว, สรุปการจับคู่)
    """

    out = lines.copy()

    for c in ("เลขที่ใบกำกับ", "ใบสั่งขาย", "วันที่ IK"):
        out[c] = ""

    blocks = blocks_of(lines)

    stats = {"code": 0, "exact": 0, "by_order": 0, "blocks_unpaired": 0, "invoices_unpaired": 0}

    chan_map = {"Online": CH_ONLINE, "Call Center": CH_CALL}

    has_text = "รายละเอียด" in csv_orders.columns

    for csv_name, ch in chan_map.items():

        bl = blocks[blocks["ช่องทางการเปิดบิล"] == ch].reset_index(drop=True)
        iv = csv_orders[csv_orders["ประเภทช่องทาง"] == csv_name]
        iv = iv.sort_values("เลขที่ใบกำกับสินค้า").reset_index(drop=True)

        if bl.empty:
            stats["invoices_unpaired"] += len(iv)
            continue

        if iv.empty:
            stats["blocks_unpaired"] += len(bl)
            continue

        pair, used_i = {}, set()

        def take(bi, ii, key):
            pair[bi] = ii
            stats.setdefault("methods", {})[(ch, bl.at[bi, "รหัสลูกค้า"])] = key
            used_i.add(ii)
            stats[key] += 1

        if has_text:      # 0) รหัสลูกค้าอยู่ในข้อความของใบกำกับ

            for bi, brow in bl.iterrows():

                hit = [
                    ii for ii, irow in iv.iterrows()
                    if ii not in used_i and _has_code(irow["รายละเอียด"], brow["รหัสลูกค้า"])
                ]

                if len(hit) == 1:
                    take(bi, hit[0], "code")

        for bi, brow in bl.iterrows():     # 1) ยอดตรงเป๊ะ

            if bi in pair:
                continue

            for ii, irow in iv.iterrows():

                if ii not in used_i and abs(float(irow["ยอดขาย"]) - brow["ยอดขาย"]) < 0.005:
                    take(bi, ii, "exact")
                    break

        rest_b = [i for i in range(len(bl)) if i not in pair]
        rest_i = [i for i in range(len(iv)) if i not in used_i]

        if rest_b and rest_i:

            # ที่เหลือจับคู่ตามยอดที่ใกล้กันที่สุดก่อน (ไม่ใช้ลำดับเลขใบกำกับ เพราะบล็อกกับใบกำกับเรียงไม่ตรงกัน)
            # จำนวนเท่ากัน → จับให้หมด · จำนวนไม่เท่ากัน → จับเฉพาะคู่ที่ยอดต่างไม่เกิน 25% (กันจับมั่ว)
            same_n = len(rest_b) == len(rest_i)

            cand = sorted(
                (abs(float(iv.at[ii, "ยอดขาย"]) - float(bl.at[bi, "ยอดขาย"])), bi, ii)
                for bi in rest_b for ii in rest_i
            )

            done_b, done_i = set(), set()

            for d, bi, ii in cand:

                if bi in done_b or ii in done_i:
                    continue

                base = max(float(bl.at[bi, "ยอดขาย"]), float(iv.at[ii, "ยอดขาย"]), 1.0)

                if not same_n and d / base > 0.25:
                    continue

                done_b.add(bi)
                done_i.add(ii)
                take(bi, ii, "by_order")

            stats["blocks_unpaired"] += len(rest_b) - len(done_b)
            stats["invoices_unpaired"] += len(rest_i) - len(done_i)

        else:
            stats["blocks_unpaired"] += len(rest_b)
            stats["invoices_unpaired"] += len(rest_i)

        for bi, ii in pair.items():

            mask = (
                (out["ช่องทางการเปิดบิล"] == ch)
                & (out["รหัสลูกค้า"] == bl.at[bi, "รหัสลูกค้า"])
            )

            out.loc[mask, "เลขที่ใบกำกับ"] = str(iv.at[ii, "เลขที่ใบกำกับสินค้า"])
            out.loc[mask, "ใบสั่งขาย"] = str(iv.at[ii, "ใบสั่งขาย"])
            out.loc[mask, "วันที่ IK"] = str(iv.at[ii, "วันที่"]) if "วันที่" in iv.columns else ""

    return out, stats


def restore_cancelled(lines: pd.DataFrame, all_lines: pd.DataFrame, csv_orders: pd.DataFrame):
    """ออเดอร์ที่ Shipnity ระบุว่ายกเลิก แต่ Express ลงบิลไว้แล้ว → คืนเข้าบล็อกเดิม

    ดูทีละบล็อกที่จับคู่กับใบกำกับแล้ว ถ้ายอด CSV มากกว่ายอดบล็อก และมีออเดอร์ยกเลิกในบล็อกเดียวกัน
    (ช่องทาง + รหัสลูกค้า) ที่ยอดรวม 1–3 ออเดอร์เท่ากับส่วนต่างพอดี → ถือว่าเป็นออเดอร์ที่ลงบิลไปแล้ว
    คืน (lines ใหม่, DataFrame รายการที่คืน)
    """

    from itertools import combinations

    empty = pd.DataFrame(columns=["เลขที่ออเดอร์", "ยอดขาย", "เลขที่ใบกำกับ", "รหัสลูกค้า"])

    if all_lines is None or lines.empty or "ยกเลิก" not in all_lines.columns:
        return lines, empty

    canc = all_lines[all_lines["ยกเลิก"] & ~all_lines["เลขที่ออเดอร์"].isin(lines["เลขที่ออเดอร์"])]

    if canc.empty:
        return lines, empty

    csv_amt = csv_orders.drop_duplicates("เลขที่ใบกำกับสินค้า").set_index(
        csv_orders.drop_duplicates("เลขที่ใบกำกับสินค้า")["เลขที่ใบกำกับสินค้า"].astype(str)
    )["ยอดขาย"].astype(float)

    add, rows = [], []

    blocks = lines[lines["เลขที่ใบกำกับ"] != ""].drop_duplicates("เลขที่ออเดอร์")

    for (ch, code, inv), g in blocks.groupby(["ช่องทางการเปิดบิล", "รหัสลูกค้า", "เลขที่ใบกำกับ"]):

        if inv not in csv_amt.index:
            continue

        diff = round(float(csv_amt[inv]) - float(g["ยอดขาย"].sum()), 2)

        if diff <= 0.005:
            continue

        cand = canc[(canc["ช่องทางการเปิดบิล"] == ch) & (canc["รหัสลูกค้า"] == code)].drop_duplicates("เลขที่ออเดอร์")

        pick = None

        for k in (1, 2, 3):
            for combo in combinations(cand.index, k):
                if abs(cand.loc[list(combo), "ยอดขาย"].sum() - diff) < 0.005:
                    pick = cand.loc[list(combo), "เลขที่ออเดอร์"].tolist()
                    break
            if pick:
                break

        if not pick:
            continue

        ref = g.iloc[0]

        for o in pick:
            x = canc[canc["เลขที่ออเดอร์"] == o].copy()
            x["ยกเลิก"] = False
            x["เลขที่ใบกำกับ"], x["ใบสั่งขาย"], x["วันที่ IK"] = ref["เลขที่ใบกำกับ"], ref["ใบสั่งขาย"], ref["วันที่ IK"]
            add.append(x)
            rows.append({"เลขที่ออเดอร์": o, "ยอดขาย": float(x["ยอดขาย"].iloc[0]), "เลขที่ใบกำกับ": inv, "รหัสลูกค้า": code})

    if not add:
        return lines, empty

    return pd.concat([lines, *add], ignore_index=True), pd.DataFrame(rows)


def _subsets_sum(amounts, target_cents, max_k=3):
    """หาชุดออเดอร์ (1–3 ตัว) ที่ยอดรวมเท่าเป้า → [[index,...], ...] (amounts เป็นสตางค์)"""

    idx = range(len(amounts))
    found = []

    by_amt = {}
    for i in idx:
        by_amt.setdefault(amounts[i], []).append(i)

    for i in by_amt.get(target_cents, []):
        found.append([i])

    for i in idx:
        for j in by_amt.get(target_cents - amounts[i], []):
            if j > i:
                found.append([i, j])

    if max_k >= 3:
        for i in idx:
            for j in range(i + 1, len(amounts)):
                rest = target_cents - amounts[i] - amounts[j]
                for k in by_amt.get(rest, []):
                    if k > j:
                        found.append([i, j, k])

        if len(found) > 200:
            found = found[:200]

    return found


def rebalance_blocks(lines: pd.DataFrame, csv_orders: pd.DataFrame, csv_items=None, known=None):
    """Express ลงบิลออเดอร์ไว้คนละใบกับที่แอปจัดกลุ่ม (เช่น แอปใส่ออเดอร์ Flash ไว้กลุ่ม SPX แต่ Express ลงเป็น J&T)

    อาการ: ใบกำกับสองใบในช่องทางเดียวกัน ยอดต่างจาก CSV เท่ากันแต่เครื่องหมายตรงข้าม (+X กับ −X)
    → หาออเดอร์ (1–3 ออเดอร์) ในบล็อกที่เกิน ที่ยอดรวม = X (ถ้ามีรายการสินค้าจาก CSV ใช้ยืนยันด้วย)
    แล้วย้ายไปบล็อกที่ขาด คืน (lines ใหม่, DataFrame รายการที่ย้าย)
    """

    from collections import Counter

    cols = ["เลขที่ออเดอร์", "ยอดขาย", "ขนส่ง", "จากใบกำกับ", "ไปใบกำกับ", "ช่องทาง", "ยืนยันด้วยสินค้า"]
    empty = pd.DataFrame(columns=cols)

    if lines.empty or "เลขที่ใบกำกับ" not in lines.columns:
        return lines, empty

    out = lines.copy()
    out["รหัสสินค้า (เทียบ)"] = out["รหัสสินค้า (ดิบ)"].map(lambda c: norm_code(strip_prefix(c, known)))

    csv_amt = csv_orders.drop_duplicates("เลขที่ใบกำกับสินค้า")
    csv_amt = dict(zip(csv_amt["เลขที่ใบกำกับสินค้า"].astype(str), csv_amt["ยอดขาย"].astype(float)))

    def item_counter(df):
        return Counter(dict(df.groupby("รหัสสินค้า (เทียบ)")["จำนวน"].sum()))

    moved = []
    used = set()

    inv_orders = out[out["เลขที่ใบกำกับ"].astype(str) != ""].drop_duplicates("เลขที่ออเดอร์")

    blk = (
        inv_orders.groupby(["ช่องทางการเปิดบิล", "รหัสลูกค้า", "เลขที่ใบกำกับ"], as_index=False)["ยอดขาย"].sum()
    )
    blk["diff"] = (blk["ยอดขาย"] - blk["เลขที่ใบกำกับ"].astype(str).map(csv_amt)).round(2)
    blk = blk.dropna(subset=["diff"])

    for ch, g in blk.groupby("ช่องทางการเปิดบิล"):

        over = g[g["diff"] > 0.005]
        under = g[g["diff"] < -0.005]

        for _, o in over.iterrows():

            for _, u in under.iterrows():

                if str(u["เลขที่ใบกำกับ"]) in used or str(o["เลขที่ใบกำกับ"]) in used:
                    continue

                if abs(o["diff"] + u["diff"]) > 0.005:
                    continue

                cand = inv_orders[
                    (inv_orders["ช่องทางการเปิดบิล"] == ch)
                    & (inv_orders["รหัสลูกค้า"] == o["รหัสลูกค้า"])
                ].reset_index(drop=True)

                subsets = _subsets_sum([int(round(a * 100)) for a in cand["ยอดขาย"]], int(round(o["diff"] * 100)))

                if not subsets:
                    continue

                pick, by_items = None, False

                if csv_items is not None and len(csv_items):

                    ci = csv_items[
                        (csv_items["เลขที่ใบกำกับ"].astype(str) == str(u["เลขที่ใบกำกับ"]))
                        & (csv_items["รหัสสินค้า"].astype(str) != "4230")
                    ]
                    ub = out[out["เลขที่ใบกำกับ"].astype(str) == str(u["เลขที่ใบกำกับ"])]

                    need = Counter(dict(ci.groupby("รหัสสินค้า")["จำนวน CSV"].sum())) - item_counter(ub)

                    if need:
                        for sub in subsets:
                            orders_sub = set(cand.loc[sub, "เลขที่ออเดอร์"])
                            if item_counter(out[out["เลขที่ออเดอร์"].isin(orders_sub)]) == need:
                                pick, by_items = sub, True
                                break

                if pick is None and len(subsets) == 1:
                    pick = subsets[0]

                if pick is None:
                    continue

                nos = list(cand.loc[pick, "เลขที่ออเดอร์"])
                ref = out[out["เลขที่ใบกำกับ"].astype(str) == str(u["เลขที่ใบกำกับ"])].iloc[0]
                mask = out["เลขที่ออเดอร์"].isin(nos)

                out.loc[mask, "รหัสลูกค้า"] = u["รหัสลูกค้า"]
                out.loc[mask, "เลขที่ใบกำกับ"] = ref["เลขที่ใบกำกับ"]
                out.loc[mask, "ใบสั่งขาย"] = ref["ใบสั่งขาย"]
                out.loc[mask, "วันที่ IK"] = ref["วันที่ IK"]

                for no in nos:
                    r = cand[cand["เลขที่ออเดอร์"] == no].iloc[0]
                    moved.append({
                        "เลขที่ออเดอร์": no, "ยอดขาย": float(r["ยอดขาย"]), "ขนส่ง": r["ขนส่ง"],
                        "จากใบกำกับ": str(o["เลขที่ใบกำกับ"]), "ไปใบกำกับ": str(u["เลขที่ใบกำกับ"]),
                        "ช่องทาง": ch, "ยืนยันด้วยสินค้า": "ใช่" if by_items else "ไม่ (เจอชุดเดียวที่ยอดตรง)",
                    })

                used.add(str(o["เลขที่ใบกำกับ"]))
                used.add(str(u["เลขที่ใบกำกับ"]))

                break

    out = out.drop(columns=["รหัสสินค้า (เทียบ)"])

    return out, (pd.DataFrame(moved, columns=cols) if moved else empty)


# =========================================================
# lines → ไฟล์ Excel แบบบล็อก (เหมือนรายงานโปรโมชั่นที่เคลียร์แล้ว)
# =========================================================

def to_block_xlsx(lines: pd.DataFrame) -> bytes:
    """1 บล็อก = 1 (ช่องทาง, รหัสลูกค้า) ลำดับคอลัมน์ตามไฟล์ที่เคลียร์แล้ว"""

    if lines.empty:
        raise ValueError("ไม่มีข้อมูลบรรทัดสินค้า")

    d = lines.copy()

    hdr = [None] * 16
    hdr[0] = "ช่องทางการเปิดบิล"

    rows = []

    for (ch, cust), blk in d.groupby(["ช่องทางการเปิดบิล", "รหัสลูกค้า"], sort=True):

        # ชื่อกลุ่ม = ขนส่งที่มีออเดอร์มากสุดในบล็อก (ใช้แยกขนส่ง/วิธีชำระในหน้าภาพรวม)
        grp = (
            blk.drop_duplicates("เลขที่ออเดอร์")["ขนส่ง"].value_counts().index[0]
        )

        invoice = next((x for x in blk["เลขที่ใบกำกับ"] if x), None)
        sk = next((x for x in blk["ใบสั่งขาย"] if x), None)
        ik_date = next((x for x in blk["วันที่ IK"] if x), None)

        g = [None] * 16
        g[4] = grp
        rows.append(g)
        rows.append(hdr)

        for _no, od in blk.groupby("เลขที่ออเดอร์", sort=False):

            for i, (_, r) in enumerate(od.iterrows()):

                row = [None] * 16
                row[0] = ch
                row[1] = cust
                row[3] = r["รหัสสินค้า"] if "รหัสสินค้า" in od.columns else r["รหัสสินค้า (ดิบ)"]
                row[4] = r["ชื่อรายการ"]
                row[5] = r["จำนวน"]
                row[6] = r["ราคา"]
                row[7] = r["มูลค่าสุทธิ"]

                if i == 0:
                    row[8] = r["ค่าส่ง"]
                    row[9] = r["ยอดขาย"]
                    row[10] = r["เลขที่ออเดอร์"]
                    row[11] = r["ส่วนลด"]
                    row[12] = r["ขนส่ง"]
                    row[13] = sk

                row[14] = invoice
                row[15] = ik_date
                rows.append(row)

    out = io.BytesIO()
    pd.DataFrame(rows).to_excel(out, header=False, index=False, engine="openpyxl")

    return out.getvalue()


# =========================================================
# ตรวจการจับคู่ (ให้ผู้ใช้ดูว่าฟิลด์ตรงกับของจริงไหม)
# =========================================================

def mapping_check(lines: pd.DataFrame) -> dict:

    orders = lines.drop_duplicates("เลขที่ออเดอร์")

    by_ch = (
        orders.groupby(["ช่องทางการเปิดบิล", "contactMethod"], dropna=False)
        .size().reset_index(name="ออเดอร์")
        .sort_values("ออเดอร์", ascending=False)
    )

    blocks = blocks_of(lines)

    ships = (
        orders.groupby(["รหัสลูกค้า", "ขนส่ง"]).size().reset_index(name="ออเดอร์")
    )

    return {
        "orders": len(orders),
        "lines": len(lines),
        "blocks": blocks,
        "by_channel": by_ch,
        "ships": ships,
        "unknown": sorted(x for x in blocks["รหัสลูกค้า"] if str(x).startswith("ไม่ทราบ")),
    }


def time_profile(lines: pd.DataFrame) -> pd.DataFrame:
    """จำนวนบรรทัด/ออเดอร์ แยกตามชั่วโมงที่พิมพ์ (ไว้ดูว่าข้อมูลครอบคลุมช่วงเวลาไหน)"""

    t = pd.to_datetime(lines["วันที่พิมพ์"], format="%d/%m/%Y %H:%M", errors="coerce")

    d = lines.assign(_d=t.dt.strftime("%d/%m/%Y"), _h=t.dt.hour)

    return (
        d.groupby(["_d", "_h"])
        .agg(บรรทัด=("เลขที่ออเดอร์", "size"), ออเดอร์=("เลขที่ออเดอร์", "nunique"))
        .reset_index()
        .rename(columns={"_d": "วันที่พิมพ์", "_h": "ชั่วโมง"})
    )


# =========================================================
# เทียบกับไฟล์ที่ export จาก Shipnity (ไว้ตรวจว่าดึงตรงไหม)
# =========================================================

EXPORT_ORDER_COL = "เลขที่ออเดอร์ (ออเดอร์)"
EXPORT_PRINTED_COL = "วันที่พิมพ์ (ออเดอร์)"


def compare_with_export(lines: pd.DataFrame, export: pd.DataFrame) -> dict:
    """เทียบข้อมูลที่ดึงจาก API กับไฟล์ export (.xlsx) ของ Shipnity ช่วงเดียวกัน"""

    if EXPORT_ORDER_COL not in export.columns:
        raise ValueError(f"ไม่ใช่ไฟล์ export รายงานโปรโมชั่น (ไม่พบคอลัมน์ {EXPORT_ORDER_COL})")

    f_orders = export[EXPORT_ORDER_COL].astype(str).str.strip()
    api = lines.drop_duplicates("เลขที่ออเดอร์")

    a_set, f_set = set(api["เลขที่ออเดอร์"]), set(f_orders)

    only_api = api[~api["เลขที่ออเดอร์"].isin(f_set)][
        ["เลขที่ออเดอร์", "วันที่พิมพ์", "ช่องทางการเปิดบิล", "ขนส่ง", "ยอดขาย", "contactMethod", "ยกเลิก"]
    ].reset_index(drop=True)

    only_file = pd.DataFrame({"เลขที่ออเดอร์": sorted(f_set - a_set)})

    if EXPORT_PRINTED_COL in export.columns:
        only_file = only_file.merge(
            export.assign(**{"เลขที่ออเดอร์": f_orders})[["เลขที่ออเดอร์", EXPORT_PRINTED_COL]]
            .drop_duplicates("เลขที่ออเดอร์"),
            on="เลขที่ออเดอร์", how="left"
        )

    def by_hour(series):
        t = pd.to_datetime(series, format="%d/%m/%Y %H:%M", errors="coerce", dayfirst=True)
        return t.dt.hour.value_counts().sort_index()

    parts = {"API": by_hour(lines["วันที่พิมพ์"])}

    if EXPORT_PRINTED_COL in export.columns:
        parts["ไฟล์ export"] = by_hour(export[EXPORT_PRINTED_COL].astype(str).str[:16])

    hours = pd.concat(parts, axis=1)
    hours.index.name = "ชั่วโมง"

    dup_cols = [c for c in ("เลขที่ออเดอร์", "รหัสสินค้า (ดิบ)", "จำนวน", "มูลค่าสุทธิ", "วันที่พิมพ์") if c in lines.columns]

    return {
        "api_lines": len(lines),
        "file_lines": len(export),
        "api_orders": len(a_set),
        "file_orders": len(f_set),
        "both": len(a_set & f_set),
        "only_api": only_api,
        "only_file": only_file,
        "hours": hours.fillna(0).astype(int).reset_index(),
        "dup_lines": int(lines.duplicated(dup_cols).sum()),
        "api_sales": round(float(api["ยอดขาย"].sum()), 2),
        "file_sales": round(float(
            export.drop_duplicates(EXPORT_ORDER_COL)["ยอดขาย (ออเดอร์)"].astype(float).sum()
        ), 2) if "ยอดขาย (ออเดอร์)" in export.columns else None,
    }