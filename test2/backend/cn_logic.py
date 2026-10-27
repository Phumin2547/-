"""Logic หน้า CN: ใบลดหนี้ / รับคืนสินค้า (Shipnity vs Express)

ไม่ import streamlit — ฟังก์ชันอ่านไฟล์รับ object ที่มี .getvalue()
"""

import re

import pandas as pd

# =========================================================
# ค่าคงที่ (แก้กฎได้ที่นี่)
# =========================================================

CN_ORDER_COL = "เลขที่ออเดอร์ (ออเดอร์)"
CN_SALES_COL = "ยอดขาย (ออเดอร์)"
CN_CHANNEL_COL = "ช่องทางที่ลูกค้าทักมา (ออเดอร์)"
CN_EMPLOYEE_COL = "รหัสพนักงาน (ออเดอร์)"

CN_CHANNELS = ["Online Marketing", "Call Center"]

# รูปแบบเลขที่ออเดอร์ที่ค้นหาในไฟล์ Express
CN_CODE_PATTERN = {
    "Online Marketing": r"\b(?:RE|MO|MX|MM|MB)\d+-\d+\b",
    "Call Center": r"\b(?:RE|MO|MX|MM|MB)\d{6}-\d+\b",
}

CN_STAFF_PATTERN = r"\b(?:VP|OB)\d+\b"

CN_NUMBER_PATTERN = r"(?<!\d)\d+(?:\.\d+)?(?!\d)"

# แถวที่มีคำว่า "รวม" ให้ใช้ตัวเลขตัวที่ 4 ของแถวเป็นยอดรวม
CN_TOTAL_NUMBER_INDEX = 3


# ---------------------------------------------------------
# แบ่ง Channel ของ Shipnity
# ---------------------------------------------------------

def classify_cn_channel(channel, employee):

    channel = str(channel).strip().lower()
    employee = str(employee).strip().upper()

    if "phone" in channel:
        return "Call Center"

    if "other" in channel and re.search(CN_STAFF_PATTERN, employee):
        return "Call Center"

    return "Online Marketing"


# ---------------------------------------------------------
# เตรียมข้อมูล Shipnity (ใบรับคืน)
# ---------------------------------------------------------

def prepare_cn_shipnity(df):

    required = [CN_ORDER_COL, CN_SALES_COL, CN_CHANNEL_COL]

    missing = [c for c in required if c not in df.columns]

    if missing:
        raise KeyError(
            "ไฟล์ Shipnity ไม่พบคอลัมน์: " + ", ".join(missing)
        )

    out = df.copy()

    # ตัดแถวที่ไม่มีเลขที่ออเดอร์ (เช่น แถวว่าง / แถวสรุปท้ายไฟล์)
    out = out[out[CN_ORDER_COL].notna()].copy()

    out["order_code"] = out[CN_ORDER_COL].astype(str).str.strip()

    out["sales"] = pd.to_numeric(
        out[CN_SALES_COL].astype(str).str.replace(",", "", regex=False),
        errors="coerce"
    ).fillna(0)

    if CN_EMPLOYEE_COL in out.columns:
        employee = out[CN_EMPLOYEE_COL]
    else:
        employee = pd.Series("", index=out.index)

    out["Channel_Category"] = [
        classify_cn_channel(c, e)
        for c, e in zip(out[CN_CHANNEL_COL], employee)
    ]

    return out


# ---------------------------------------------------------
# อ่านไฟล์ Express (CSV รายงาน encoding cp874)
# ---------------------------------------------------------

def read_express_lines(uploaded):

    if uploaded is None:
        return []

    text = uploaded.getvalue().decode("cp874", errors="replace")

    return text.splitlines()


def extract_express_codes(lines, pattern):

    codes = []

    for line in lines:
        codes.extend(re.findall(pattern, line))

    return codes


def extract_express_total(lines, number_index=CN_TOTAL_NUMBER_INDEX):

    rows = []

    for no, line in enumerate(lines, start=1):

        if "รวม" not in line:
            continue

        numbers = [
            float(m)
            for m in re.findall(CN_NUMBER_PATTERN, line)
        ]

        if len(numbers) > number_index:

            rows.append(
                {
                    "แถว": no,
                    "ข้อความในแถว": line.strip(),
                    "ยอดที่ใช้": numbers[number_index],
                }
            )

    return pd.DataFrame(
        rows,
        columns=["แถว", "ข้อความในแถว", "ยอดที่ใช้"]
    )


# ---------------------------------------------------------
# เปรียบเทียบ Shipnity vs Express
# ---------------------------------------------------------

def build_cn_result(ship_raw, online_lines, call_lines):

    ship = prepare_cn_shipnity(ship_raw)

    express_lines = {
        "Online Marketing": online_lines,
        "Call Center": call_lines,
    }

    summary_rows = []
    tables = {}
    totals = {}
    found_codes = {}

    for channel in CN_CHANNELS:

        # ----- Shipnity (รวมยอดต่อออเดอร์) -----

        ship_detail = (
            ship[ship["Channel_Category"] == channel]
            .groupby("order_code", as_index=False)["sales"]
            .sum()
            .rename(
                columns={
                    "order_code": "รหัส",
                    "sales": "ยอดเงิน_Shipnity",
                }
            )
        )

        ship_detail["key"] = ship_detail["รหัส"].str.upper()

        # ----- Express -----

        lines = express_lines[channel]

        raw_codes = extract_express_codes(
            lines,
            CN_CODE_PATTERN[channel]
        )

        express_keys = {c.strip().upper() for c in raw_codes}

        total_rows = extract_express_total(lines)

        express_sales = float(total_rows["ยอดที่ใช้"].sum())

        ship_keys = set(ship_detail["key"])

        # ----- แยกกลุ่ม -----

        cols = ["รหัส", "ยอดเงิน_Shipnity"]

        only_ship = (
            ship_detail[~ship_detail["key"].isin(express_keys)][cols]
            .sort_values("รหัส")
            .reset_index(drop=True)
        )

        both = (
            ship_detail[ship_detail["key"].isin(express_keys)][cols]
            .sort_values("รหัส")
            .reset_index(drop=True)
        )

        only_express = pd.DataFrame(
            {"รหัส": sorted(express_keys - ship_keys)}
        )

        tables[channel] = {
            "only_ship": only_ship,
            "only_express": only_express,
            "both": both,
        }

        totals[channel] = total_rows

        found_codes[channel] = {
            "raw": len(raw_codes),
            "unique": len(express_keys),
        }

        summary_rows.append(
            {
                "Channel": channel,
                "จำนวนรายการ_Shipnity": len(ship_detail),
                "ยอดเงิน_Shipnity": float(
                    ship_detail["ยอดเงิน_Shipnity"].sum()
                ),
                "จำนวนรายการ_Express": len(express_keys),
                "ยอดเงิน_Express": express_sales,
            }
        )

    summary = pd.DataFrame(summary_rows)

    total = {"Channel": "รวม"}

    for col in summary.columns[1:]:
        total[col] = summary[col].sum()

    summary = pd.concat(
        [summary, pd.DataFrame([total])],
        ignore_index=True
    )

    summary["ส่วนต่างจำนวนรายการ"] = (
        summary["จำนวนรายการ_Shipnity"]
        - summary["จำนวนรายการ_Express"]
    )

    summary["ส่วนต่างยอดเงิน"] = (
        summary["ยอดเงิน_Shipnity"]
        - summary["ยอดเงิน_Express"]
    )

    return {
        "ship": ship,
        "summary": summary,
        "tables": tables,
        "totals": totals,
        "found_codes": found_codes,
    }
