"""หน้า "รายละเอียดออเดอร์" — เทียบใบกำกับ Express (Online / Call Center) กับ Shipnity โปรโมชั่น

แบ่งเป็น 4 แท็บ ข้อมูลแต่ละอย่างแสดงที่เดียว:
    📊 ภาพรวม          เทียบยอด CSV vs Shipnity + สรุปตามขนส่ง
    ✅ ตรวจใบกำกับ      สถานะรายใบกำกับ IK / WG / IE
    🧩 รายการสินค้า      ออเดอร์และรหัสสินค้าในแต่ละใบกำกับ
    🔎 ค้นหาออเดอร์      ค้นหาเลขออเดอร์ ดูรายบรรทัด

ไฟล์ที่ใช้: 1) Shipnity โปรโมชั่น (.xlsx)  2) Express Online (.csv)  3) Express Call Center (.csv)
"""

import io
import re

import pandas as pd
import plotly.express as px
import streamlit as st

from ui import (
    card,
    chip,
    esc,
    file_chips,
    fmt_money,
    html_table,
    kpi_cards,
    page_controls,
    page_header,
    page_slice,
    section_title,
    stat_rows,
)
from utils import money

FILES_KEY = "od_files"          # {ช่องอัปโหลด: {"name", "data"}}
COUNTER_KEY = "od_up_counts"    # ตัวนับ key ของช่องอัปโหลด (ไว้ล้างช่องหลังเลือกไฟล์)
RAN_KEY = "od_ran"


# =========================================================
# ส่วนประมวลผล + แสดงผล (พอร์ตจากโน้ตบุ๊ก)
# =========================================================

INV_CHANNEL_COL, INV_CUSTOMER_COL, INV_GROUP_COL, INV_SALES_COL, INV_ORDER_COL = 0, 1, 4, 9, 10
INV_NO_COL, INV_CODE_COL, INV_NAME_COL, INV_QTY_COL, INV_NET_COL = 14, 3, 4, 5, 7
INV_SHIPPING_CODE = "4230"   # ค่าจัดส่ง: CSV เป็นบรรทัดสินค้า, Shipnity เป็นคอลัมน์ค่าส่ง จึงไม่เทียบจำนวน
INV_NO_RE = r"^[A-Z]{2}\d+$"


def _csv_lines(data):
    """CSV รายงาน Express → DataFrame คอลัมน์แรก = ข้อความ 1 บรรทัด
    (อ่านเป็นบรรทัดตรง ๆ กันคอมมาในตัวเลข เช่น 1,541.00 ทำให้บรรทัดขาด)"""

    for enc in ["utf-8-sig", "cp874", "tis-620"]:

        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("cp874", errors="replace")

    lines = [
        ln.strip('"') if ln.startswith('"') and ln.endswith('"') else ln
        for ln in text.splitlines()
    ]

    return pd.DataFrame({"line": lines[1:]})   # ข้ามบรรทัดหัวเหมือน read_csv


def _inv_norm_code(x):
    """ทำรหัสสินค้าให้เทียบกันได้ ('W TEST HAP1' ↔ 'W_TEST_HAP1', ตัดเลข 0 หน้ารหัสตัวเลขล้วน)"""

    x = re.sub(r"[\s\xa0_]+", "_", str(x).strip()).upper()

    return x.lstrip("0") if x.isdigit() else x


def _parse_invoice_report(df, channel_name):
    """1 บรรทัดหัวบิล = 1 ใบกำกับ, ยอดขาย = “รวมทั้งสิ้น” (ทศนิยมตัวสุดท้ายก่อนวันครบกำหนด)"""

    pat = re.compile(
        r"^\s*(\d{2}/\d{2}/\d{2})\s+([A-Z]{2}\d+)\s+(.*?)"
        r"\s+(\d{2}/\d{2}/\d{2})\s+([A-Z]{2}\d+)\s+([YN])\s*$"
    )

    rows = []

    for line in df.iloc[:, 0].dropna().astype(str):

        m = pat.match(line.strip())

        if not m:
            continue

        date, inv, middle, _due, so, _paid = m.groups()

        amounts = re.findall(r"(?<![A-Z])\d[\d,]*\.\d{2}", middle)

        if not amounts:
            continue

        rows.append({
            "ประเภทช่องทาง": channel_name, "วันที่": date,
            "เลขที่ใบกำกับสินค้า": inv, "ใบสั่งขาย": so,
            "ยอดขาย": float(amounts[-1].replace(",", "")),
        })

    return pd.DataFrame(
        rows,
        columns=["ประเภทช่องทาง", "วันที่", "เลขที่ใบกำกับสินค้า", "ใบสั่งขาย", "ยอดขาย"]
    )


def _parse_csv_items(df, channel_name):
    """รายการสินค้าในแต่ละใบกำกับของ CSV"""

    inv_pat = re.compile(r"^\s*\d{2}/\d{2}/\d{2}\s+([A-Z]{2}\d+)\s")
    item_pat = re.compile(r"^\s+(\d+)\s+(\S+)\s+(.*?)\s+[A-Z]{2}\d+-\s*(\d+)\s*$")

    rows, cur = [], None

    for raw in df.iloc[:, 0].dropna().astype(str):

        line = raw.replace("\xa0", " ").rstrip()

        m = inv_pat.match(line)

        if m:
            cur = m.group(1)
            continue

        m = item_pat.match(line)

        if not m or cur is None:
            continue

        _no, code, middle, _so_line = m.groups()

        toks = middle.split()

        nums = []

        while toks and re.fullmatch(r"-?\d[\d,]*\.\d{2}", toks[-1]):
            nums.insert(0, float(toks.pop().replace(",", "")))

        if not toks or not re.match(r"^\d+\D", toks[-1]):
            continue

        qty = int(re.match(r"^\d+", toks.pop()).group())

        rows.append({
            "เลขที่ใบกำกับ": cur, "ประเภทช่องทาง": channel_name,
            "รหัสสินค้า": _inv_norm_code(code), "ชื่อรายการ (CSV)": " ".join(toks),
            "จำนวน CSV": qty,
            "จำนวนเงิน CSV": nums[-1] if nums else 0.0,
        })

    return pd.DataFrame(
        rows,
        columns=["เลขที่ใบกำกับ", "ประเภทช่องทาง", "รหัสสินค้า",
                 "ชื่อรายการ (CSV)", "จำนวน CSV", "จำนวนเงิน CSV"]
    )


def _carrier_of(group):
    """ชื่อกลุ่มของบล็อก Shipnity → (ขนส่ง, วิธีชำระ)
    เช่น "Kerry COD /SK" → (Kerry, COD) · "DHL โอนเงิน/SE" → (DHL, โอนเงิน)
    กลุ่มมาร์เก็ตเพลส (Lazada/TikTok/Shopee) ไม่มีขนส่งในชื่อ จึงแยกเป็นกลุ่มของตัวเอง"""

    g = str(group).strip().lower()

    for key, name in [
        ("kerry", "Kerry"), ("dhl", "DHL"), ("speed", "Speed"),
        ("lazada", "Lazada"), ("tiktok", "TikTok"),
        ("shoppee", "Shopee"), ("shopee", "Shopee"),
    ]:
        if key in g:
            carrier = name
            break
    else:
        carrier = "อื่นๆ (ลูกค้าองค์กร)"

    pay = "COD" if "cod" in g else "โอนเงิน" if "โอน" in g else "-"

    return carrier, pay


@st.cache_data(show_spinner=False)
def _invoice_compare(promo_data, online_data, call_data):
    """คืน dict ผลเทียบทั้งหมด"""

    df_online = _csv_lines(online_data)
    df_call = _csv_lines(call_data)
    df_promo = pd.read_excel(io.BytesIO(promo_data), header=None)

    on_orders = _parse_invoice_report(df_online, "Online")
    cc_orders = _parse_invoice_report(df_call, "Call Center")

    # ---------- Shipnity: แยกบล็อกตามหัวตาราง ----------

    header_rows = [
        r for r in range(len(df_promo))
        if str(df_promo.iat[r, INV_CHANNEL_COL]).strip() == "ช่องทางการเปิดบิล"
    ]

    if not header_rows:
        raise ValueError("ไม่พบหัวตาราง “ช่องทางการเปิดบิล” ในไฟล์ Shipnity โปรโมชั่น")

    bounds = header_rows + [len(df_promo)]

    records = []

    for block_no, (start, end) in enumerate(zip(bounds, bounds[1:]), 1):

        block = df_promo.iloc[start + 1:end]

        if block.empty:
            continue

        channel = str(block.iat[0, INV_CHANNEL_COL]).strip()

        group = df_promo.iat[start - 1, INV_GROUP_COL] if start > 0 else None

        for _, row in block.iterrows():

            order_no = row[INV_ORDER_COL]

            if pd.isna(order_no) or str(order_no).strip() == "":
                continue

            records.append({
                "บล็อก": block_no,
                "กลุ่ม": str(group).strip(),
                "ช่องทางการเปิดบิล": channel,
                "เลขที่ออเดอร์": str(order_no).strip(),
                "ยอดขาย": pd.to_numeric(row[INV_SALES_COL], errors="coerce"),
            })

    ship_orders = pd.DataFrame(
        records,
        columns=["บล็อก", "กลุ่ม", "ช่องทางการเปิดบิล", "เลขที่ออเดอร์", "ยอดขาย"]
    ).drop_duplicates(subset=["เลขที่ออเดอร์"])

    # ---------- 1) ตารางเปรียบเทียบรวมตามช่องทาง ----------

    def ship_summary(channel):

        d = ship_orders[ship_orders["ช่องทางการเปิดบิล"] == channel]

        return d["บล็อก"].nunique(), d["เลขที่ออเดอร์"].nunique(), d["ยอดขาย"].sum()

    on_bill, on_ord, on_sales = ship_summary("Online/SK")
    cc_bill, cc_ord, cc_sales = ship_summary("Callcenter/SE")

    csv_on_n, csv_on_s = on_orders["เลขที่ใบกำกับสินค้า"].nunique(), on_orders["ยอดขาย"].sum()
    csv_cc_n, csv_cc_s = cc_orders["เลขที่ใบกำกับสินค้า"].nunique(), cc_orders["ยอดขาย"].sum()

    def srow(name, cn, cs, sb, so, ss):
        return {
            "ประเภทช่องทาง": name, "จำนวนบิล CSV": cn, "จำนวนบิล Shipnity": sb,
            "ผลต่างจำนวนบิล": sb - cn, "จำนวนออเดอร์ Shipnity": so,
            "ยอดขาย CSV": cs, "ยอดขาย Shipnity": ss,
            "ผลต่างยอดขาย": round(ss - cs, 2) + 0.0,
        }

    comparison = pd.DataFrame([
        srow("Online", csv_on_n, csv_on_s, on_bill, on_ord, on_sales),
        srow("Call Center", csv_cc_n, csv_cc_s, cc_bill, cc_ord, cc_sales),
        srow("รวมทั้งหมด", csv_on_n + csv_cc_n, csv_on_s + csv_cc_s,
             on_bill + cc_bill, on_ord + cc_ord, on_sales + cc_sales),
    ])

    # ---------- 2) ขนส่ง / วิธีชำระ ของแต่ละบล็อก ----------

    carrier_blocks = (
        ship_orders.groupby(["บล็อก", "ช่องทางการเปิดบิล", "กลุ่ม"], sort=True)
        .agg(ออเดอร์=("เลขที่ออเดอร์", "nunique"), ยอด_Shipnity=("ยอดขาย", "sum"))
        .reset_index()
    )

    carrier_blocks[["ขนส่ง", "ชำระ"]] = [_carrier_of(g) for g in carrier_blocks["กลุ่ม"]]

    csv_all = pd.concat([on_orders, cc_orders], ignore_index=True)

    # ---------- 3) ตรวจเลขที่ใบกำกับ IK / WG / IE ----------

    df_csv_items = pd.concat(
        [_parse_csv_items(df_online, "Online"), _parse_csv_items(df_call, "Call Center")],
        ignore_index=True
    )

    ps = df_promo.copy()

    is_header = ps[0].astype(str).str.strip().eq("ช่องทางการเปิดบิล")

    ps["_blk"] = is_header.cumsum()

    ps = ps[(ps["_blk"] > 0) & ~is_header].copy()

    inv_ok = ps[INV_NO_COL].astype(str).str.strip().str.match(INV_NO_RE)

    ps["_inv"] = (
        ps[INV_NO_COL].where(inv_ok)
        .groupby(ps["_blk"]).transform(lambda x: x.ffill().bfill())
    )

    sp = ps[ps[INV_CODE_COL].notna() & ps["_inv"].notna()]

    df_ship_items = pd.DataFrame({
        "เลขที่ใบกำกับ": sp["_inv"].astype(str).str.strip(),
        "รหัสสินค้า": sp[INV_CODE_COL].map(_inv_norm_code),
        "ชื่อรายการ (Shipnity)": sp[INV_NAME_COL].astype(str).str.strip(),
        "จำนวน Shipnity": pd.to_numeric(sp[INV_QTY_COL], errors="coerce"),
        "มูลค่าสุทธิ Shipnity": pd.to_numeric(sp[INV_NET_COL], errors="coerce"),
    })

    ord_rows = df_promo[
        df_promo[INV_ORDER_COL].notna()
        & df_promo[INV_NO_COL].notna()
        & df_promo[INV_NO_COL].astype(str).str.match(INV_NO_RE)
    ]

    ship_inv = (
        ord_rows.assign(
            inv=ord_rows[INV_NO_COL].astype(str).str.strip(),
            s=pd.to_numeric(ord_rows[INV_SALES_COL], errors="coerce")
        )
        .groupby("inv")
        .agg(ออเดอร์=(INV_ORDER_COL, "nunique"), ยอด_Shipnity=("s", "sum"))
        .reset_index()
        .rename(columns={"inv": "เลขที่ใบกำกับ"})
    )

    csv_inv = csv_all[["ประเภทช่องทาง", "เลขที่ใบกำกับสินค้า", "ยอดขาย"]].rename(
        columns={"เลขที่ใบกำกับสินค้า": "เลขที่ใบกำกับ", "ยอดขาย": "ยอด_CSV"}
    )

    inv_check = csv_inv.merge(ship_inv, on="เลขที่ใบกำกับ", how="outer", indicator=True)

    inv_check["ผลต่าง"] = (
        inv_check["ยอด_Shipnity"].fillna(0) - inv_check["ยอด_CSV"].fillna(0)
    ).round(2) + 0.0

    inv_check["สถานะ"] = inv_check.apply(
        lambda r: "ไม่มีใน Shipnity" if r["_merge"] == "left_only"
        else "ไม่มีใน CSV" if r["_merge"] == "right_only"
        else "ตรงกัน" if abs(r["ผลต่าง"]) < 0.005 else "ยอดไม่ตรง",
        axis=1
    )

    inv_check = inv_check.drop(columns="_merge").sort_values("เลขที่ใบกำกับ").reset_index(drop=True)

    # ขนส่ง/ชำระ ของแต่ละใบกำกับ (บล็อกเดียวกับที่มีเลขใบกำกับนั้น)
    blk_inv = ps.dropna(subset=["_inv"]).groupby("_blk")["_inv"].first().astype(str).str.strip()

    inv_carrier = carrier_blocks.copy()

    inv_carrier["เลขที่ใบกำกับ"] = inv_carrier["บล็อก"].map(blk_inv)

    inv_carrier = (
        inv_carrier.dropna(subset=["เลขที่ใบกำกับ"])
        .drop_duplicates("เลขที่ใบกำกับ")[["เลขที่ใบกำกับ", "กลุ่ม", "ขนส่ง", "ชำระ"]]
    )

    inv_check = inv_check.merge(inv_carrier, on="เลขที่ใบกำกับ", how="left")

    # ---------- 4) เทียบรายการสินค้าตามรหัส (ไม่รวมค่าจัดส่ง) ----------

    key = ["เลขที่ใบกำกับ", "รหัสสินค้า"]

    c = (
        df_csv_items[df_csv_items["รหัสสินค้า"] != INV_SHIPPING_CODE]
        .groupby(key)
        .agg(name_csv=("ชื่อรายการ (CSV)", "first"), qty_csv=("จำนวน CSV", "sum"),
             amt_csv=("จำนวนเงิน CSV", "sum"))
        .reset_index()
    )

    s = (
        df_ship_items[df_ship_items["รหัสสินค้า"] != INV_SHIPPING_CODE]
        .groupby(key)
        .agg(name_ship=("ชื่อรายการ (Shipnity)", "first"), qty_ship=("จำนวน Shipnity", "sum"),
             amt_ship=("มูลค่าสุทธิ Shipnity", "sum"))
        .reset_index()
    )

    items = c.merge(s, on=key, how="outer")

    items[["qty_csv", "qty_ship"]] = items[["qty_csv", "qty_ship"]].fillna(0)

    items["name"] = items["name_ship"].fillna(items["name_csv"])

    items["diff"] = items["qty_ship"] - items["qty_csv"]

    items["status"] = items["diff"].apply(
        lambda d: "ตรงกัน" if d == 0 else "Shipnity มากกว่า" if d > 0 else "CSV มากกว่า"
    )

    items = items.rename(columns={
        "name": "ชื่อรายการ", "qty_csv": "จำนวน CSV", "qty_ship": "จำนวน Shipnity",
        "diff": "ผลต่างจำนวน", "amt_csv": "เงิน CSV", "amt_ship": "เงิน Shipnity",
        "status": "สถานะ",
    })

    items = items[key + ["ชื่อรายการ", "จำนวน CSV", "จำนวน Shipnity", "ผลต่างจำนวน",
                         "เงิน CSV", "เงิน Shipnity", "สถานะ"]]

    return {
        "comparison": comparison,
        "inv_check": inv_check,
        "items": items,
        "carrier_blocks": carrier_blocks,
        "ship_blocks": len(header_rows),
        "ship_orders": len(ship_orders),
        "csv_bills": (len(on_orders), len(cc_orders)),
    }


INV_STATUS_TONE = {
    "ตรงกัน": "green",
    "ยอดไม่ตรง": "amber",
    "ไม่มีใน Shipnity": "red",
    "ไม่มีใน CSV": "red",
}

# สีพื้นของคอลัมน์ "สถานะ" ในตาราง (ตัวอักษรเข้มเสมอ อ่านง่ายทั้งโหมดสว่าง/มืด)
STATUS_BG = {
    "ตรงกัน": "#DDF3E4",
    "ยอดไม่ตรง": "#FFF0C7",
    "Shipnity มากกว่า": "#FFF0C7",
    "CSV มากกว่า": "#FAD9D9",
    "ไม่มีใน Shipnity": "#FAD9D9",
    "ไม่มีใน CSV": "#FAD9D9",
}


def _paint_status(col):
    """ระบายสีคอลัมน์สถานะ ใช้กับ Styler.apply(subset=["สถานะ"])"""

    return [
        f"background-color: {STATUS_BG[v]}; color: #1F2937" if v in STATUS_BG else ""
        for v in col
    ]


# =========================================================
# ข้อมูลระดับออเดอร์ (Shipnity)
# =========================================================

@st.cache_data(show_spinner=False)
def _build_order_detail(promo_data):
    """แปลงรายงาน Shipnity แบบบล็อกเป็นตารางรายบรรทัดสินค้า (lines) และรายออเดอร์ (orders)"""

    df = pd.read_excel(io.BytesIO(promo_data), header=None)

    required_max_col = max(INV_CHANNEL_COL, INV_GROUP_COL, INV_SALES_COL, INV_ORDER_COL, 14)

    if df.shape[1] <= required_max_col:
        raise ValueError(
            f"ไฟล์ Shipnity มี {df.shape[1]} คอลัมน์ แต่ต้องมีอย่างน้อย {required_max_col + 1} คอลัมน์"
        )

    is_header = df[0].astype(str).str.strip().eq("ช่องทางการเปิดบิล")
    block_ids = is_header.cumsum()
    lines = []

    for block_no in range(1, int(block_ids.max()) + 1):

        header_idx = df.index[(block_ids == block_no) & is_header]

        if len(header_idx) == 0:
            continue

        hdr_idx = header_idx[0]
        group_name = df.iat[hdr_idx - 1, INV_GROUP_COL] if hdr_idx > 0 else ""
        block = df[(block_ids == block_no) & ~is_header].copy()

        if block.empty:
            continue

        channel = str(block.iloc[0, INV_CHANNEL_COL]).strip()
        inv_vals = block.iloc[:, INV_NO_COL].astype(str).str.strip()
        inv_vals = inv_vals[inv_vals.str.match(INV_NO_RE, na=False)]
        invoice = inv_vals.iloc[0] if len(inv_vals) else None

        # แถวที่มีรหัสสินค้า ผูกกับเลขออเดอร์ล่าสุดในบล็อก
        current_order, current_head = None, None

        for _, row in block.iterrows():

            order_value = row.iloc[INV_ORDER_COL]

            if pd.notna(order_value) and str(order_value).strip():
                current_order = str(order_value).strip()
                current_head = row

            code_value = row.iloc[INV_CODE_COL]

            if current_order is None or pd.isna(code_value) or not str(code_value).strip():
                continue

            head = current_head

            lines.append({
                "เลขที่ออเดอร์": current_order,
                "บล็อก": block_no,
                "ช่องทาง": channel,
                "กลุ่ม": "" if pd.isna(group_name) else str(group_name).strip(),
                "เลขที่ใบกำกับ": invoice,
                "ใบสั่งขาย": head.iloc[13],
                "ขนส่ง": head.iloc[12],
                "ค่าส่ง": pd.to_numeric(head.iloc[8], errors="coerce"),
                "ส่วนลด": pd.to_numeric(head.iloc[11], errors="coerce"),
                "ยอดขาย": pd.to_numeric(head.iloc[INV_SALES_COL], errors="coerce"),
                "รหัสสินค้า": _inv_norm_code(code_value),
                "ชื่อรายการ": "" if pd.isna(row.iloc[INV_NAME_COL]) else str(row.iloc[INV_NAME_COL]).strip(),
                "จำนวน": pd.to_numeric(row.iloc[INV_QTY_COL], errors="coerce"),
                "ราคา": pd.to_numeric(row.iloc[6], errors="coerce"),
                "มูลค่าสุทธิ": pd.to_numeric(row.iloc[7], errors="coerce"),
            })

    lines_df = pd.DataFrame(lines)

    if lines_df.empty:
        return lines_df, pd.DataFrame()

    order_rows = []

    for order_no, group in lines_df.groupby("เลขที่ออเดอร์", sort=False, dropna=False):

        first = group.iloc[0]

        items_text = group.apply(
            lambda r: f"{r['รหัสสินค้า']} {r['ชื่อรายการ']}"
                      + (f" ×{r['จำนวน']:g}" if pd.notna(r["จำนวน"]) else ""),
            axis=1
        ).tolist()

        order_rows.append({
            "เลขที่ออเดอร์": order_no,
            "ช่องทาง": first["ช่องทาง"],
            "เลขที่ใบกำกับ": first["เลขที่ใบกำกับ"],
            "กลุ่ม": first["กลุ่ม"],
            "ขนส่ง": first["ขนส่ง"],
            "ยอดขาย": group["ยอดขาย"].dropna().iloc[0] if group["ยอดขาย"].notna().any() else 0,
            "ค่าส่ง": first["ค่าส่ง"],
            "ส่วนลด": first["ส่วนลด"],
            "จำนวนรายการ": len(group),
            "จำนวนชิ้นรวม": group["จำนวน"].sum(),
            "รายการสินค้า": " | ".join(items_text),
        })

    return lines_df, pd.DataFrame(order_rows)


@st.cache_data(show_spinner=False)
def _excel_bytes(promo_data, online_data, call_data):
    """ไฟล์ Excel สรุปผลทั้งหมด (สร้างครั้งเดียว เก็บแคช)"""

    res = _invoice_compare(promo_data, online_data, call_data)
    lines_df, orders_df = _build_order_detail(promo_data)

    out = io.BytesIO()

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        res["comparison"].to_excel(writer, sheet_name="เทียบยอด CSV Shipnity", index=False)
        res["inv_check"].to_excel(writer, sheet_name="ตรวจใบกำกับ", index=False)
        res["items"].to_excel(writer, sheet_name="เทียบรายการสินค้า", index=False)
        orders_df.to_excel(writer, sheet_name="รายออเดอร์", index=False)
        lines_df.to_excel(writer, sheet_name="รายการสินค้าทั้งหมด", index=False)

    return out.getvalue()


# =========================================================
# แท็บ 1: ภาพรวม
# =========================================================

def _carrier_summary(blocks):
    """สรุปตามขนส่ง / วิธีชำระ"""

    with card("od_carrier"):

        section_title(
            "สรุปตามขนส่ง",
            "แยกจากชื่อกลุ่มของบล็อกใน Shipnity (Kerry / DHL / Speed · COD / โอนเงิน)"
        )

        by = (
            blocks.groupby(["ขนส่ง", "ชำระ"], as_index=False)
            .agg(บล็อก=("บล็อก", "nunique"), ออเดอร์=("ออเดอร์", "sum"),
                 ยอดขาย=("ยอด_Shipnity", "sum"))
        )

        by["เฉลี่ย/ออเดอร์"] = by["ยอดขาย"] / by["ออเดอร์"].where(by["ออเดอร์"] > 0)
        by["% ยอดขาย"] = by["ยอดขาย"] / max(by["ยอดขาย"].sum(), 1) * 100
        by = by.sort_values("ยอดขาย", ascending=False).reset_index(drop=True)

        stat_rows([
            ("💵", "ยอด COD ที่ต้องเก็บ", money(by.loc[by["ชำระ"] == "COD", "ยอดขาย"].sum())),
            ("🏦", "ยอดโอนเงิน", money(by.loc[by["ชำระ"] == "โอนเงิน", "ยอดขาย"].sum())),
        ])

        show = by.copy()

        for c in ["ยอดขาย", "เฉลี่ย/ออเดอร์"]:
            show[c] = show[c].map(lambda v: "-" if pd.isna(v) else f"{v:,.2f}")

        st.dataframe(
            show,
            column_config={
                "% ยอดขาย": st.column_config.ProgressColumn(
                    "% ยอดขาย", format="%.1f%%", min_value=0, max_value=100
                ),
            },
            use_container_width=True,
            hide_index=True
        )

        with st.expander("ดูแยกตามช่องทางเปิดบิล (จำนวนออเดอร์)"):

            st.dataframe(
                pd.crosstab(
                    blocks["ขนส่ง"], blocks["ช่องทางการเปิดบิล"],
                    values=blocks["ออเดอร์"], aggfunc="sum", margins=True, margins_name="รวม"
                ).fillna(0).astype(int),
                use_container_width=True
            )


def _tab_overview(res):

    comp = res["comparison"]
    tot = comp[comp["ประเภทช่องทาง"] == "รวมทั้งหมด"].iloc[0]

    with card("od_inv_sum"):

        section_title(
            "เปรียบเทียบยอดขาย CSV กับ Shipnity",
            "CSV นับใบกำกับ · Shipnity นับบล็อก (1 บล็อก = 1 ใบกำกับ) · ผลต่าง = Shipnity − CSV"
        )

        if abs(tot["ผลต่างยอดขาย"]) < 0.005 and tot["ผลต่างจำนวนบิล"] == 0:
            st.success("ยอดขายและจำนวนบิลรวมตรงกัน")
        else:
            st.warning("พบผลต่างระหว่าง CSV กับ Shipnity — ดูว่าใบไหนไม่ตรงได้ที่แท็บ “ตรวจใบกำกับ”")

        st.dataframe(
            comp.style.format({
                "จำนวนบิล CSV": "{:,.0f}", "จำนวนบิล Shipnity": "{:,.0f}",
                "ผลต่างจำนวนบิล": "{:+,.0f}", "จำนวนออเดอร์ Shipnity": "{:,.0f}",
                "ยอดขาย CSV": "{:,.2f}", "ยอดขาย Shipnity": "{:,.2f}",
                "ผลต่างยอดขาย": "{:+,.2f}",
            }),
            use_container_width=True,
            hide_index=True
        )

    _carrier_summary(res["carrier_blocks"])


# =========================================================
# แท็บ 2: ตรวจใบกำกับ
# =========================================================

def _tab_check(inv):

    with card("od_inv_check"):

        section_title(
            "ตรวจเลขที่ใบกำกับ (IK / WG / IE)",
            "เลขใบกำกับใน CSV มีใน Shipnity หรือไม่ และยอดตรงกันไหม"
        )

        n = len(inv)

        kpi_cards([
            {"label": "ตรงกัน", "count": int((inv["สถานะ"] == "ตรงกัน").sum()),
             "total": n, "tone": "green"},
            {"label": "ยอดไม่ตรง", "count": int((inv["สถานะ"] == "ยอดไม่ตรง").sum()),
             "total": n, "tone": "amber"},
            {"label": "มีฝั่งเดียว", "count": int(inv["สถานะ"].isin(["ไม่มีใน Shipnity", "ไม่มีใน CSV"]).sum()),
             "total": n, "tone": "red"},
        ])

        f1, f2, f3, f4 = st.columns([2, 2, 3, 2], vertical_alignment="bottom")

        with f1:
            status = st.selectbox("สถานะ", ["ทั้งหมด"] + list(INV_STATUS_TONE), key="od_inv_status")

        with f2:
            carrier = st.selectbox(
                "ขนส่ง", ["ทั้งหมด"] + sorted(inv["ขนส่ง"].dropna().unique()), key="od_inv_carrier"
            )

        with f3:
            q = st.text_input(
                "🔍 ค้นหาเลขที่ใบกำกับ", placeholder="เช่น WG6900965", key="od_inv_q"
            ).strip().upper()

        view = inv

        if status != "ทั้งหมด":
            view = view[view["สถานะ"] == status]

        if carrier != "ทั้งหมด":
            view = view[view["ขนส่ง"] == carrier]

        if q:
            view = view[view["เลขที่ใบกำกับ"].astype(str).str.upper().str.contains(q, regex=False)]

        with f4:
            st.download_button(
                "⬇️ ดาวน์โหลดตารางนี้ (CSV)",
                data=view.to_csv(index=False).encode("utf-8-sig"),
                file_name="invoice_check.csv",
                mime="text/csv",
                use_container_width=True,
                key="od_inv_dl"
            )

        if view.empty:
            st.info("ไม่พบใบกำกับตามตัวกรองนี้ ลองเปลี่ยนสถานะหรือล้างช่องค้นหา")
            return

        st.caption(f"พบ {len(view):,} ใบกำกับ")

        cols = [
            ("ลำดับ", lambda r, n: str(n), "c"),
            ("ช่องทาง", lambda r, n: esc(r["ประเภทช่องทาง"]), "l"),
            ("เลขที่ใบกำกับ", lambda r, n: f'<b>{esc(r["เลขที่ใบกำกับ"])}</b>', "l"),
            ("ขนส่ง", lambda r, n: esc(r["ขนส่ง"]), "l"),
            ("ชำระ", lambda r, n: esc(r["ชำระ"]), "l"),
            ("ออเดอร์", lambda r, n: "-" if pd.isna(r["ออเดอร์"]) else f'{r["ออเดอร์"]:,.0f}', "r"),
            ("ยอด CSV", lambda r, n: fmt_money(r["ยอด_CSV"]), "r"),
            ("ยอด Shipnity", lambda r, n: fmt_money(r["ยอด_Shipnity"]), "r"),
            ("ผลต่าง", lambda r, n: (
                f'<span class="{"neg" if abs(r["ผลต่าง"]) >= 0.005 else ""}">{r["ผลต่าง"]:,.2f}</span>'
            ), "r"),
            ("สถานะ", lambda r, n: chip(r["สถานะ"], INV_STATUS_TONE[r["สถานะ"]]), "l"),
        ]

        page_df, start = page_slice(view, "od_inv_tbl")

        html_table(page_df, cols, start)

        page_controls("od_inv_tbl", len(view), start)


# =========================================================
# แท็บ 3: รายการสินค้ารายใบกำกับ
# =========================================================

def _invoice_orders_view(orders_df, lines_df, invoice_no):
    """ใบกำกับที่เลือกมีออเดอร์อะไรบ้าง กี่ออเดอร์ กี่ชิ้น (จาก Shipnity)"""

    od = orders_df[orders_df["เลขที่ใบกำกับ"].astype(str) == str(invoice_no)] \
        if not orders_df.empty else orders_df

    if od.empty:
        st.info(f"ใบกำกับ {invoice_no} ไม่มีออเดอร์ใน Shipnity")
        return

    ln = lines_df[lines_df["เลขที่ใบกำกับ"].astype(str) == str(invoice_no)]

    a, b, c = st.columns(3)
    a.metric("จำนวนออเดอร์", f"{od['เลขที่ออเดอร์'].nunique():,}")
    b.metric("รายการสินค้า (บรรทัด)", f"{len(ln):,}")
    c.metric("จำนวนชิ้นรวม", f"{od['จำนวนชิ้นรวม'].sum():,.0f}")

    with st.expander(f"ออเดอร์ในใบกำกับ {invoice_no}", expanded=True):

        st.dataframe(
            od[["เลขที่ออเดอร์", "ยอดขาย", "ค่าส่ง", "ส่วนลด", "จำนวนรายการ",
                "จำนวนชิ้นรวม", "รายการสินค้า"]]
            .reset_index(drop=True)
            .style.format({
                "ยอดขาย": "{:,.2f}", "ค่าส่ง": "{:,.2f}", "ส่วนลด": "{:,.2f}",
                "จำนวนรายการ": "{:,.0f}", "จำนวนชิ้นรวม": "{:,.0f}",
            }, na_rep="-"),
            use_container_width=True,
            hide_index=True
        )


def _tab_items(res, orders_df, lines_df):

    inv, items = res["inv_check"], res["items"]

    bad = set(inv.loc[inv["สถานะ"] != "ตรงกัน", "เลขที่ใบกำกับ"]) | set(
        items.loc[items["สถานะ"] != "ตรงกัน", "เลขที่ใบกำกับ"]
    )

    all_inv = sorted(set(inv["เลขที่ใบกำกับ"]) | set(items["เลขที่ใบกำกับ"]))
    ordered = [i for i in all_inv if i in bad] + [i for i in all_inv if i not in bad]

    with card("od_inv_items"):

        section_title(
            "รหัสสินค้า / ชื่อรายการ รายใบกำกับ",
            "เทียบจำนวน CSV กับ Shipnity ตามรหัสสินค้า (ไม่รวมค่าจัดส่ง รหัส " + INV_SHIPPING_CODE + ")"
        )

        mode = st.radio(
            "แสดง",
            ["เฉพาะใบที่ไม่ตรง", "เลือกดูทีละใบกำกับ"],
            horizontal=True,
            key="od_inv_mode"
        )

        if mode == "เลือกดูทีละใบกำกับ":

            if not ordered:
                st.info("ไม่มีใบกำกับให้เลือก")
                return

            pick = st.selectbox(
                "เลขที่ใบกำกับ (⚠️ = ไม่ตรง แสดงก่อน)",
                ordered,
                format_func=lambda i: f"⚠️ {i}" if i in bad else f"✅ {i}",
                key="od_inv_pick"
            )

            _invoice_orders_view(orders_df, lines_df, pick)

            detail = items[items["เลขที่ใบกำกับ"] == pick].drop(columns="เลขที่ใบกำกับ")

            if detail.empty:
                st.info("ไม่มีรายการสินค้าให้เทียบในใบกำกับนี้")
                return

            st.markdown("**เทียบรายการสินค้า**")

            sort_cols = ["รหัสสินค้า"]

        else:

            detail = items[items["เลขที่ใบกำกับ"].isin(bad) & (items["สถานะ"] != "ตรงกัน")]

            if detail.empty:
                st.success("ทุกใบกำกับตรงกัน: ยอดเท่ากัน และรหัสสินค้า/จำนวนตรงกันทุกรายการ")
                return

            st.caption(f"พบ {len(detail):,} รายการที่จำนวนไม่ตรง ใน {detail['เลขที่ใบกำกับ'].nunique():,} ใบกำกับ")

            sort_cols = ["เลขที่ใบกำกับ", "รหัสสินค้า"]

        st.dataframe(
            detail.sort_values(sort_cols).reset_index(drop=True)
            .style.format({
                "จำนวน CSV": "{:,.0f}", "จำนวน Shipnity": "{:,.0f}",
                "ผลต่างจำนวน": "{:+,.0f}", "เงิน CSV": "{:,.2f}", "เงิน Shipnity": "{:,.2f}",
            }, na_rep="-")
            .apply(_paint_status, subset=["สถานะ"]),
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# แท็บ 4: ค้นหาออเดอร์
# =========================================================

def _tab_orders(res, orders_df, lines_df):

    with card("od_order_detail"):

        section_title(
            "ค้นหาออเดอร์",
            "พิมพ์เลขออเดอร์เต็มหรือบางส่วน คั่นหลายเลขด้วยช่องว่างหรือจุลภาค"
        )

        if orders_df.empty:
            st.warning("ไม่พบรายการสินค้าที่มีรหัสสินค้าและเลขออเดอร์ในไฟล์ Shipnity")
            return

        f1, f2 = st.columns([4, 3], vertical_alignment="bottom")

        with f1:
            query = st.text_input(
                "เลขที่ออเดอร์", placeholder="เช่น 261016-151 หรือ 261016-151, 261016-152",
                key="od_order_search"
            ).strip()

        with f2:
            show_bad = st.toggle("เฉพาะออเดอร์ในใบกำกับที่ไม่ตรง", key="od_order_suspect")

        view = orders_df

        if query:
            terms = [x for x in re.split(r"[\s,]+", query) if x]
            mask = pd.Series(False, index=view.index)

            for term in terms:
                mask |= view["เลขที่ออเดอร์"].astype(str).str.contains(
                    re.escape(term), case=False, na=False
                )

            view = view[mask]

        if show_bad:
            inv, item = res["inv_check"], res["items"]
            bad = set(inv.loc[inv["สถานะ"] != "ตรงกัน", "เลขที่ใบกำกับ"].dropna())
            bad |= set(item.loc[item["สถานะ"] != "ตรงกัน", "เลขที่ใบกำกับ"].dropna())
            view = view[view["เลขที่ใบกำกับ"].isin(bad)]

        if view.empty:
            st.info("ไม่พบออเดอร์ที่ตรงกับคำค้น ลองพิมพ์เลขบางส่วนหรือปิดตัวกรอง")
            return

        st.caption(f"แสดง {len(view):,} จาก {len(orders_df):,} ออเดอร์")

        st.dataframe(
            view.reset_index(drop=True).style.format(
                {"ยอดขาย": "{:,.2f}", "ค่าส่ง": "{:,.2f}", "ส่วนลด": "{:,.2f}",
                 "จำนวนรายการ": "{:,.0f}", "จำนวนชิ้นรวม": "{:,.0f}"}, na_rep="-"
            ),
            use_container_width=True,
            hide_index=True
        )

        selected = st.selectbox(
            "ดูรายการสินค้ารายบรรทัดของออเดอร์",
            view["เลขที่ออเดอร์"].astype(str).tolist(),
            key="od_order_pick"
        )

        detail = lines_df[lines_df["เลขที่ออเดอร์"].astype(str) == selected]

        st.dataframe(
            detail[["รหัสสินค้า", "ชื่อรายการ", "จำนวน", "ราคา", "มูลค่าสุทธิ"]]
            .reset_index(drop=True)
            .style.format({"จำนวน": "{:,.0f}", "ราคา": "{:,.2f}", "มูลค่าสุทธิ": "{:,.2f}"}, na_rep="-"),
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# อัปโหลด
# =========================================================

def _upload_block():
    """3 ช่องอัปโหลด + ปุ่มประมวลผล (พับเก็บอัตโนมัติหลังประมวลผลแล้ว)"""

    files = st.session_state.setdefault(FILES_KEY, {})
    counts = st.session_state.setdefault(COUNTER_KEY, {})

    def slot(sid, label, types):

        n = counts.get(sid, 0)

        up = st.file_uploader(label, type=types, key=f"od_up_{sid}_{n}")

        if up:
            files[sid] = {"name": up.name, "data": up.getvalue()}
            counts[sid] = n + 1
            st.rerun()

    with st.expander("📁 อัปโหลดไฟล์", expanded=not st.session_state.get(RAN_KEY, False)):

        r1 = st.columns([3, 3, 3, 2], vertical_alignment="bottom")

        with r1[0]:
            slot("promo", "1) Shipnity โปรโมชั่น (.xlsx)", ["xlsx", "xls"])

        with r1[1]:
            slot("online", "2) Express Online (.csv)", ["csv", "txt"])

        with r1[2]:
            slot("call", "3) Express Call Center (.csv)", ["csv", "txt"])

        with r1[3]:
            run = st.button("🚀 ประมวลผล", type="primary", use_container_width=True, key="od_run")

    file_chips([
        ("โปรโมชั่น", "promo" in files),
        ("Express Online", "online" in files),
        ("Express Call Center", "call" in files),
    ])

    return files, run


# =========================================================
# หน้าหลัก
# =========================================================

def render_order_detail_page():

    page_header(
        "🔎",
        "รายละเอียดออเดอร์",
        "อัปโหลด Shipnity โปรโมชั่น และ Express Online / Call Center "
        "เพื่อเทียบใบกำกับและตรวจรหัสสินค้า"
    )

    files, run = _upload_block()

    if run:

        if not all(k in files for k in ("promo", "online", "call")):
            st.warning("อัปโหลดให้ครบทั้ง 3 ไฟล์ก่อนกดประมวลผล")
            st.session_state[RAN_KEY] = False
            return

        st.session_state[RAN_KEY] = True

    if not st.session_state.get(RAN_KEY):
        st.info("อัปโหลดไฟล์ทั้ง 3 แล้วกด 🚀 ประมวลผล")
        return

    if not all(k in files for k in ("promo", "online", "call")):
        st.warning("ไฟล์ไม่ครบ อัปโหลดให้ครบทั้ง 3 ไฟล์แล้วกด 🚀 ประมวลผลอีกครั้ง")
        return

    promo, online, call = files["promo"]["data"], files["online"]["data"], files["call"]["data"]

    try:
        with st.spinner("กำลังเทียบข้อมูล..."):
            res = _invoice_compare(promo, online, call)
    except Exception as e:  # noqa: BLE001
        st.error(f"เทียบใบกำกับไม่ได้: {e} — ตรวจว่าเลือกไฟล์ถูกช่องและเป็นรายงานรุ่นเดิม")
        return

    try:
        lines_df, orders_df = _build_order_detail(promo)
    except Exception as e:  # noqa: BLE001
        st.error(f"สร้างรายละเอียดออเดอร์ไม่ได้: {e}")
        lines_df, orders_df = pd.DataFrame(), pd.DataFrame()

    _, dl = st.columns([5, 2])

    with dl:
        st.download_button(
            "⬇️ ดาวน์โหลดผลตรวจทั้งหมด (Excel)",
            data=_excel_bytes(promo, online, call),
            file_name="orders_summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="od_order_excel"
        )

    t1, t2, t3, t4 = st.tabs(["📊 ภาพรวม", "✅ ตรวจใบกำกับ", "🧩 รายการสินค้า", "🔎 ค้นหาออเดอร์"])

    with t1:
        _tab_overview(res)

    with t2:
        _tab_check(res["inv_check"])

    with t3:
        _tab_items(res, orders_df, lines_df)

    with t4:
        _tab_orders(res, orders_df, lines_df)