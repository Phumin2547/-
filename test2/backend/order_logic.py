"""Logic หน้า "ตรวจสอบออเดอร์" (ไม่ import streamlit)"""

import pandas as pd

from backend.channel import classify_channel
from backend.cn_logic import extract_express_total, read_express_lines
from backend.utils import clean_channel_col, clean_order_col

# ไฟล์ Express แต่ละประเภท → ชื่อ Channel
EXPRESS_CHANNELS = ["Online Marketing", "Call Center"]

STATUS_BOTH = "มีทั้ง Shipnity และใบรายงาน"
STATUS_ONLY_SHIP = "มีเฉพาะ Shipnity"
STATUS_ONLY_REPORT = "มีเฉพาะใบรายงาน"


def build_express_totals(online_file, call_file):
    """อ่านยอดรวมจากไฟล์ Express ด้วยหลักการเดียวกับหน้า CN
    (แถวที่มีคำว่า "รวม" → ใช้ตัวเลขตัวที่ 4 ของแถว)

    คืน {channel: DataFrame แถวรวมที่พบ | None ถ้าไม่ได้อัปโหลดไฟล์}
    """

    files = {
        "Online Marketing": online_file,
        "Call Center": call_file,
    }

    out = {}

    for channel, f in files.items():

        if f is None:
            out[channel] = None
            continue

        out[channel] = extract_express_total(read_express_lines(f))

    return out


def _found_cols(df, limit=12):
    """ข้อความบอกคอลัมน์ที่อ่านเจอ ใช้ต่อท้าย error เพื่อดูว่าอัปโหลดไฟล์ผิดช่องหรือไม่"""

    cols = [str(c) for c in df.columns[:limit]]

    more = " ..." if len(df.columns) > limit else ""

    return f" (คอลัมน์ที่อ่านได้: {', '.join(cols)}{more})"


def _employee_col(df):

    if "รหัสพนักงาน" in df.columns:
        return "รหัสพนักงาน"

    if "รหัสพนักงาน (ออเดอร์)" in df.columns:
        return "รหัสพนักงาน (ออเดอร์)"

    return None


# =========================================================
# Prepare Shipnity
# =========================================================

def prepare_shipnity(df):

    df = df.copy()

    order_col = clean_order_col(df)

    if not order_col:
        raise ValueError(
            "ไม่พบคอลัมน์ออเดอร์ในไฟล์ Shipnity: "
            "ต้องมี 'เลขที่ออเดอร์' หรือ 'order_number'"
            + _found_cols(df)
        )

    if "ยอดขาย" not in df.columns:
        raise ValueError("ไม่พบคอลัมน์ 'ยอดขาย' ในไฟล์ Shipnity")

    channel_col = clean_channel_col(df)

    if not channel_col:
        raise ValueError("ไม่พบคอลัมน์ช่องทางในไฟล์ Shipnity")

    df["ยอดขาย"] = pd.to_numeric(
        df["ยอดขาย"].astype(str).str.replace(",", "", regex=False),
        errors="coerce"
    )

    df[order_col] = df[order_col].astype(str).str.strip()

    df = classify_channel(df, channel_col, _employee_col(df))

    return df, order_col, channel_col


# =========================================================
# Prepare Report
# =========================================================

def prepare_report(df):

    df = df.copy()

    # แถวว่างทั้งแถว
    df = df.dropna(how="all")

    order_col = clean_order_col(df)

    if not order_col:
        raise ValueError(
            "ไม่พบคอลัมน์ออเดอร์ในไฟล์ใบรายงาน: "
            "ต้องมี 'order_number' หรือ 'เลขที่ออเดอร์'"
            + _found_cols(df)
            + " — ตรวจว่าไฟล์ที่ใส่ในช่อง 'ใบรายงาน' ถูกไฟล์"
        )

    channel_col = clean_channel_col(df)

    if not channel_col:
        raise ValueError("ไม่พบคอลัมน์ช่องทางในไฟล์ใบรายงาน")

    if "ยอดขาย" not in df.columns:
        raise ValueError("ไม่พบคอลัมน์ 'ยอดขาย' ในไฟล์ใบรายงาน")

    # ตัดแถวที่ไม่มีเลขออเดอร์
    df = df[
        df[order_col].notna()
        &
        (df[order_col].astype(str).str.strip() != "")
    ].copy()

    # ตัดแถวที่เป็นหัวตาราง
    df = df[
        ~df[channel_col].astype(str).str.contains(
            "ช่องทางที่ลูกค้าทักมา", na=False
        )
        &
        ~df[channel_col].astype(str).str.contains(
            "ช่องทางการขาย", na=False
        )
    ].copy()

    df["ยอดขาย"] = pd.to_numeric(
        df["ยอดขาย"].astype(str).str.replace(",", "", regex=False),
        errors="coerce"
    )

    df[order_col] = df[order_col].astype(str).str.strip()

    df = classify_channel(df, channel_col, _employee_col(df))

    return df, order_col, channel_col


# =========================================================
# Build Comparison
# =========================================================

def build_comparison(ship, ship_order, report, report_order):

    # ---------------- Shipnity (1 แถว / ออเดอร์) ----------------

    s = ship[[ship_order, "ยอดขาย", "Channel_Category"]].copy()

    s["ยอดขาย"] = pd.to_numeric(s["ยอดขาย"], errors="coerce")

    s = (
        s.groupby(ship_order, as_index=False)
        .agg(
            ยอดขาย_Shipnity=("ยอดขาย", "sum"),
            Channel_Category_Shipnity=("Channel_Category", "first")
        )
        .rename(columns={ship_order: "เลขที่ออเดอร์"})
    )

    # ---------------- Report (1 แถว / ออเดอร์) ----------------

    r = report[[report_order, "ยอดขาย", "Channel_Category"]].copy()

    r["ยอดขาย"] = pd.to_numeric(r["ยอดขาย"], errors="coerce")

    r = (
        r.groupby(report_order, as_index=False)
        .agg(
            ยอดขาย_ใบรายงาน=("ยอดขาย", "sum"),
            Channel_Category_ใบรายงาน=("Channel_Category", "first")
        )
        .rename(columns={report_order: "order_number"})
    )

    # ---------------- Merge ----------------

    compare = pd.merge(
        s,
        r,
        left_on="เลขที่ออเดอร์",
        right_on="order_number",
        how="outer",
        indicator=True
    )

    # _merge เป็น Categorical → แปลงเป็น string ก่อน replace
    compare["_merge"] = compare["_merge"].astype("string")

    compare["_merge"] = compare["_merge"].replace(
        {
            "left_only": STATUS_ONLY_SHIP,
            "right_only": STATUS_ONLY_REPORT,
            "both": STATUS_BOTH,
        }
    )

    # ---------------- ส่วนต่างยอดขาย ----------------

    compare["ส่วนต่างยอดขาย"] = (
        compare["ยอดขาย_Shipnity"].fillna(0)
        - compare["ยอดขาย_ใบรายงาน"].fillna(0)
    ).round(2)

    # กลุ่ม: ใช้ของ Shipnity ก่อน ถ้าไม่มีใช้ของใบรายงาน
    compare["กลุ่ม"] = (
        compare["Channel_Category_Shipnity"]
        .fillna(compare["Channel_Category_ใบรายงาน"])
    )

    # ---------------- แยกกลุ่ม ----------------

    both = compare[compare["_merge"] == STATUS_BOTH].copy()

    different = both[both["ส่วนต่างยอดขาย"].abs() > 0.01].copy()

    same = both[both["ส่วนต่างยอดขาย"].abs() <= 0.01].copy()

    only_ship = compare[compare["_merge"] == STATUS_ONLY_SHIP].copy()

    only_report = compare[compare["_merge"] == STATUS_ONLY_REPORT].copy()

    return (
        compare,
        s,
        r,
        only_ship,
        only_report,
        both,
        different,
        same
    )
