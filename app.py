import re
import io
import pandas as pd
import streamlit as st
import plotly.express as px


# =========================================================
# Streamlit Page Config
# =========================================================

st.set_page_config(
    page_title="Order Reconciliation Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# CSS
# =========================================================

st.markdown("""
<style>

:root {
    --border:#e5e7eb;
    --muted:#6b7280;
}

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
}

[data-testid="stMetric"] {
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 14px 16px;
    background: white;
}

.card {
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px;
    background: white;
    margin-bottom: 12px;
}

.small {
    color: var(--muted);
    font-size: .88rem;
}

h1, h2, h3 {
    letter-spacing: -0.02em;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# Utility
# =========================================================

def money(x):
    return f"{float(x or 0):,.2f} บาท"


# =========================================================
# Find Order Column
# =========================================================

def clean_order_col(df):

    if "เลขที่ออเดอร์" in df.columns:
        return "เลขที่ออเดอร์"

    if "order_number" in df.columns:
        return "order_number"

    return None


# =========================================================
# Find Channel Column
# =========================================================

def clean_channel_col(df):

    if "ช่องทางการขาย" in df.columns:
        return "ช่องทางการขาย"

    if "ช่องทางที่ลูกค้าทักมา" in df.columns:
        return "ช่องทางที่ลูกค้าทักมา"

    return None


# =========================================================
# Classify Channel
# =========================================================

def classify_channel(df, channel_col, employee_col=None):

    out = df.copy()

    def classify(row):

        channel = str(
            row.get(channel_col, "")
        ).strip().lower()

        employee = (
            str(row.get(employee_col, "")).strip().upper()
            if employee_col
            else ""
        )

        note = str(
            row.get("หมายเหตุ", "")
        ).strip().upper()

        # -------------------------------------------------
        # OTHER
        # -------------------------------------------------

        if "other" in channel:

            if "phone" in channel:
                return "Call Center"

            if re.search(
                r"\b(?:VP|OB)\d+\b",
                employee
            ):
                return "Call Center"

            if re.search(
                r"\b(?:VP|OB)\d+\b",
                note
            ):
                return "Call Center"

            return "Online Marketing"

        # -------------------------------------------------
        # PHONE
        # -------------------------------------------------

        if "phone" in channel:
            return "Call Center"

        # -------------------------------------------------
        # Employee VP / OB
        # -------------------------------------------------

        if re.search(
            r"\b(?:VP|OB)\d+\b",
            employee
        ):
            return "Call Center"

        # -------------------------------------------------
        # Note VP / OB
        # -------------------------------------------------

        if re.search(
            r"\b(?:VP|OB)\d+\b",
            note
        ):
            return "Call Center"

        # -------------------------------------------------
        # Default
        # -------------------------------------------------

        return "Online Marketing"

    out["Channel_Category"] = out.apply(
        classify,
        axis=1
    )

    return out


# =========================================================
# Prepare Shipnity
# =========================================================

def prepare_shipnity(df):

    df = df.copy()

    # -----------------------------------------------------
    # Order
    # -----------------------------------------------------

    order_col = clean_order_col(df)

    if not order_col:

        raise ValueError(
            "ไม่พบคอลัมน์ออเดอร์ในไฟล์ Shipnity: "
            "ต้องมี 'เลขที่ออเดอร์' หรือ 'order_number'"
        )

    # -----------------------------------------------------
    # Sales
    # -----------------------------------------------------

    if "ยอดขาย" not in df.columns:

        raise ValueError(
            "ไม่พบคอลัมน์ 'ยอดขาย' ในไฟล์ Shipnity"
        )

    # -----------------------------------------------------
    # Channel
    # -----------------------------------------------------

    channel_col = clean_channel_col(df)

    if not channel_col:

        raise ValueError(
            "ไม่พบคอลัมน์ช่องทางในไฟล์ Shipnity"
        )

    # -----------------------------------------------------
    # Convert Sales
    # -----------------------------------------------------

    df["ยอดขาย"] = pd.to_numeric(
        df["ยอดขาย"]
        .astype(str)
        .str.replace(",", "", regex=False),
        errors="coerce"
    )

    # -----------------------------------------------------
    # Clean Order
    # -----------------------------------------------------

    df[order_col] = (
        df[order_col]
        .astype(str)
        .str.strip()
    )

    # -----------------------------------------------------
    # Employee
    # -----------------------------------------------------

    employee_col = (
        "รหัสพนักงาน"
        if "รหัสพนักงาน" in df.columns
        else (
            "รหัสพนักงาน (ออเดอร์)"
            if "รหัสพนักงาน (ออเดอร์)" in df.columns
            else None
        )
    )

    # -----------------------------------------------------
    # Channel Classification
    # -----------------------------------------------------

    df = classify_channel(
        df,
        channel_col,
        employee_col
    )

    return df, order_col, channel_col


# =========================================================
# Prepare Report
# =========================================================

def prepare_report(df):

    df = df.copy()

    # -----------------------------------------------------
    # Remove completely empty rows
    # -----------------------------------------------------

    df = df.dropna(
        how="all"
    )

    # -----------------------------------------------------
    # Order
    # -----------------------------------------------------

    order_col = clean_order_col(df)

    if not order_col:

        raise ValueError(
            "ไม่พบคอลัมน์ออเดอร์ในไฟล์ใบรายงาน: "
            "ต้องมี 'order_number' หรือ 'เลขที่ออเดอร์'"
        )

    # -----------------------------------------------------
    # Channel
    # -----------------------------------------------------

    channel_col = clean_channel_col(df)

    if not channel_col:

        raise ValueError(
            "ไม่พบคอลัมน์ช่องทางในไฟล์ใบรายงาน"
        )

    # -----------------------------------------------------
    # Sales
    # -----------------------------------------------------

    if "ยอดขาย" not in df.columns:

        raise ValueError(
            "ไม่พบคอลัมน์ 'ยอดขาย' ในไฟล์ใบรายงาน"
        )

    # -----------------------------------------------------
    # Remove blank orders
    # -----------------------------------------------------

    df = df[
        df[order_col].notna()
        &
        (
            df[order_col]
            .astype(str)
            .str.strip()
            != ""
        )
    ].copy()

    # -----------------------------------------------------
    # Remove header-like rows
    # -----------------------------------------------------

    df = df[
        ~df[channel_col]
        .astype(str)
        .str.contains(
            "ช่องทางที่ลูกค้าทักมา",
            na=False
        )
        &
        ~df[channel_col]
        .astype(str)
        .str.contains(
            "ช่องทางการขาย",
            na=False
        )
    ].copy()

    # -----------------------------------------------------
    # Convert Sales
    # -----------------------------------------------------

    df["ยอดขาย"] = pd.to_numeric(
        df["ยอดขาย"]
        .astype(str)
        .str.replace(",", "", regex=False),
        errors="coerce"
    )

    # -----------------------------------------------------
    # Clean Order
    # -----------------------------------------------------

    df[order_col] = (
        df[order_col]
        .astype(str)
        .str.strip()
    )

    # -----------------------------------------------------
    # Employee
    # -----------------------------------------------------

    employee_col = (
        "รหัสพนักงาน"
        if "รหัสพนักงาน" in df.columns
        else (
            "รหัสพนักงาน (ออเดอร์)"
            if "รหัสพนักงาน (ออเดอร์)" in df.columns
            else None
        )
    )

    # -----------------------------------------------------
    # Channel Classification
    # -----------------------------------------------------

    df = classify_channel(
        df,
        channel_col,
        employee_col
    )

    return df, order_col, channel_col


# =========================================================
# Build Comparison
# =========================================================

def build_comparison(
    ship,
    ship_order,
    report,
    report_order
):

    # =====================================================
    # Shipnity
    # =====================================================

    s = ship[
        [
            ship_order,
            "ยอดขาย",
            "Channel_Category"
        ]
    ].copy()

    s["ยอดขาย"] = pd.to_numeric(
        s["ยอดขาย"],
        errors="coerce"
    )

    s = (
        s.groupby(
            ship_order,
            as_index=False
        )
        .agg(
            ยอดขาย_Shipnity=(
                "ยอดขาย",
                "sum"
            ),
            Channel_Category_Shipnity=(
                "Channel_Category",
                "first"
            )
        )
        .rename(
            columns={
                ship_order: "เลขที่ออเดอร์"
            }
        )
    )

    # =====================================================
    # Report
    # =====================================================

    r = report[
        [
            report_order,
            "ยอดขาย",
            "Channel_Category"
        ]
    ].copy()

    r["ยอดขาย"] = pd.to_numeric(
        r["ยอดขาย"],
        errors="coerce"
    )

    r = (
        r.groupby(
            report_order,
            as_index=False
        )
        .agg(
            ยอดขาย_ใบรายงาน=(
                "ยอดขาย",
                "sum"
            ),
            Channel_Category_ใบรายงาน=(
                "Channel_Category",
                "first"
            )
        )
        .rename(
            columns={
                report_order: "order_number"
            }
        )
    )

    # =====================================================
    # Merge
    # =====================================================

    compare = pd.merge(
        s,
        r,
        left_on="เลขที่ออเดอร์",
        right_on="order_number",
        how="outer",
        indicator=True
    )

    # =====================================================
    # FIX Categorical _merge
    # =====================================================

    compare["_merge"] = (
        compare["_merge"]
        .astype("string")
    )

    compare["_merge"] = compare[
        "_merge"
    ].replace(
        {
            "left_only":
                "มีเฉพาะ Shipnity",

            "right_only":
                "มีเฉพาะใบรายงาน",

            "both":
                "มีทั้ง Shipnity และใบรายงาน"
        }
    )

    # =====================================================
    # Sales Difference
    # =====================================================

    compare["ส่วนต่างยอดขาย"] = (
        compare["ยอดขาย_Shipnity"]
        .fillna(0)
        -
        compare["ยอดขาย_ใบรายงาน"]
        .fillna(0)
    ).round(2)

    # =====================================================
    # Both
    # =====================================================

    both = compare[
        compare["_merge"]
        ==
        "มีทั้ง Shipnity และใบรายงาน"
    ].copy()

    # =====================================================
    # Different
    # =====================================================

    different = both[
        both["ส่วนต่างยอดขาย"]
        .abs()
        >
        0.01
    ].copy()

    # =====================================================
    # Same
    # =====================================================

    same = both[
        both["ส่วนต่างยอดขาย"]
        .abs()
        <=
        0.01
    ].copy()

    # =====================================================
    # Only Shipnity
    # =====================================================

    only_ship = compare[
        compare["_merge"]
        ==
        "มีเฉพาะ Shipnity"
    ].copy()

    # =====================================================
    # Only Report
    # =====================================================

    only_report = compare[
        compare["_merge"]
        ==
        "มีเฉพาะใบรายงาน"
    ].copy()

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


# =========================================================
# Read Excel
# =========================================================

def read_excel(
    uploaded,
    sheet_name=None
):

    if uploaded is None:
        return None

    data = uploaded.getvalue()

    if sheet_name:

        return pd.read_excel(
            io.BytesIO(data),
            sheet_name=sheet_name
        )

    return pd.read_excel(
        io.BytesIO(data)
    )


# =========================================================
# CN : ใบลดหนี้ / รับคืนสินค้า (Shipnity vs Express)
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

    if "other" in channel and re.search(
        CN_STAFF_PATTERN,
        employee
    ):
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

    out["order_code"] = (
        out[CN_ORDER_COL]
        .astype(str)
        .str.strip()
    )

    out["sales"] = pd.to_numeric(
        out[CN_SALES_COL]
        .astype(str)
        .str.replace(",", "", regex=False),
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

    text = uploaded.getvalue().decode(
        "cp874",
        errors="replace"
    )

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


# ---------------------------------------------------------
# หน้าเว็บ CN
# ---------------------------------------------------------

def render_cn_page():

    st.sidebar.markdown("## ↩️ CN Dashboard")

    st.sidebar.caption(
        "เปรียบเทียบใบลดหนี้ / รับคืนสินค้า "
        "ระหว่าง Shipnity กับ Express"
    )

    st.sidebar.markdown("### 1. อัปโหลดข้อมูล")

    cn_ship_file = st.sidebar.file_uploader(
        "Shipnity (รายการรับคืน)",
        type=["xlsx", "xls"],
        key="cn_ship"
    )

    cn_online_file = st.sidebar.file_uploader(
        "Express - Online ",
        type=["csv", "txt"],
        key="cn_online"
    )

    cn_call_file = st.sidebar.file_uploader(
        "Express - Call Center ",
        type=["csv", "txt"],
        key="cn_call"
    )

    st.sidebar.markdown("---")

    cn_run = st.sidebar.button(
        "🚀 ประมวลผล CN",
        type="primary",
        use_container_width=True,
        key="cn_run"
    )

    if "cn_result" not in st.session_state:
        st.session_state.cn_result = None

    if cn_run:

        if not (cn_ship_file and cn_online_file and cn_call_file):

            st.sidebar.error("กรุณาอัปโหลดให้ครบทั้ง 3 ไฟล์")

        else:

            try:

                with st.spinner("กำลังประมวลผลข้อมูล..."):

                    ship_raw = read_excel(cn_ship_file)

                    online_lines = read_express_lines(cn_online_file)
                    call_lines = read_express_lines(cn_call_file)

                    result = build_cn_result(
                        ship_raw,
                        online_lines,
                        call_lines
                    )

                    result["ship_raw"] = ship_raw

                st.session_state.cn_result = result

                st.sidebar.success("ประมวลผลสำเร็จ")

            except Exception as e:

                st.sidebar.error(f"ประมวลผลไม่สำเร็จ: {e}")

    st.title("↩️ CN Reconciliation Dashboard")

    st.caption(
        "ตรวจสอบรายการลดหนี้ / รับคืนสินค้า "
        "ระหว่าง Shipnity กับ Express (Online / Call Center)"
    )

    result = st.session_state.cn_result

    if result is None:

        st.markdown(
            """
            <div class="card">

            <h3>เริ่มต้นใช้งาน</h3>

            <p>
            อัปโหลดไฟล์ <b>Shipnity</b>,
            <b>Express Online</b> และ
            <b>Express Call Center</b>
            ทางด้านซ้าย แล้วกด
            <b>🚀 ประมวลผล CN</b>
            </p>

            <p class="small">
            ระบบจะแบ่ง Channel ของ Shipnity,
            ดึงเลขที่ออเดอร์และยอดรวมจากไฟล์ Express
            แล้วเปรียบเทียบจำนวนรายการ ยอดเงิน
            และรหัสที่ต่างกัน
            </p>

            </div>
            """,
            unsafe_allow_html=True
        )

        return

    summary = result["summary"]
    tables = result["tables"]

    total_row = summary[summary["Channel"] == "รวม"].iloc[0]

    tab_a, tab_b, tab_c = st.tabs(
        [
            "📊 สรุป",
            "🔎 รหัสที่ต่างกัน",
            "📄 ข้อมูลต้นฉบับ"
        ]
    )

    # -----------------------------------------------------
    # TAB : สรุป
    # -----------------------------------------------------

    with tab_a:

        st.subheader("สรุป Shipnity vs Express")

        m1, m2, m3 = st.columns(3)

        m1.metric(
            "รายการ Shipnity",
            f"{total_row['จำนวนรายการ_Shipnity']:,.0f}"
        )

        m2.metric(
            "รายการ Express",
            f"{total_row['จำนวนรายการ_Express']:,.0f}"
        )

        m3.metric(
            "ส่วนต่างจำนวนรายการ",
            f"{total_row['ส่วนต่างจำนวนรายการ']:,.0f}"
        )

        m4, m5, m6 = st.columns(3)

        m4.metric(
            "ยอดเงิน Shipnity",
            money(total_row["ยอดเงิน_Shipnity"])
        )

        m5.metric(
            "ยอดเงิน Express",
            money(total_row["ยอดเงิน_Express"])
        )

        m6.metric(
            "ส่วนต่างยอดเงิน (Shipnity − Express)",
            money(total_row["ส่วนต่างยอดเงิน"])
        )

        st.markdown("### เปรียบเทียบตาม Channel")

        st.dataframe(
            summary.style.format(
                {
                    "จำนวนรายการ_Shipnity": "{:,.0f}",
                    "ยอดเงิน_Shipnity": "{:,.2f}",
                    "จำนวนรายการ_Express": "{:,.0f}",
                    "ยอดเงิน_Express": "{:,.2f}",
                    "ส่วนต่างจำนวนรายการ": "{:,.0f}",
                    "ส่วนต่างยอดเงิน": "{:,.2f}",
                }
            ),
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            "ส่วนต่าง = Shipnity − Express "
            "(ลบ = Express มากกว่า)"
        )

        fig = px.bar(
            summary[summary["Channel"] != "รวม"],
            x="Channel",
            y=["ยอดเงิน_Shipnity", "ยอดเงิน_Express"],
            barmode="group"
        )

        fig.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
            legend_title="",
            yaxis_title="ยอดเงิน (บาท)",
            xaxis_title=""
        )

        st.plotly_chart(fig, use_container_width=True)

        for channel in CN_CHANNELS:

            if result["totals"][channel].empty:

                st.warning(
                    f"{channel}: ไม่พบแถว \"รวม\" ในไฟล์ Express "
                    "จึงนับยอดเงิน Express เป็น 0"
                )

    # -----------------------------------------------------
    # TAB : รหัสที่ต่างกัน
    # -----------------------------------------------------

    with tab_b:

        channel = st.radio(
            "Channel",
            CN_CHANNELS,
            horizontal=True,
            key="cn_channel"
        )

        t = tables[channel]

        k1, k2, k3 = st.columns(3)

        k1.metric("มีทั้ง Shipnity และ Express", f"{len(t['both']):,}")
        k2.metric("มีเฉพาะ Shipnity", f"{len(t['only_ship']):,}")
        k3.metric("มีเฉพาะ Express", f"{len(t['only_express']):,}")

        c1, c2, c3 = st.columns(3)

        with c1:

            st.markdown("#### มีทั้ง 2 ระบบ")

            st.dataframe(
                t["both"].style.format({"ยอดเงิน_Shipnity": "{:,.2f}"}),
                use_container_width=True,
                hide_index=True
            )

        with c2:

            st.markdown("#### มีเฉพาะ Shipnity")

            st.dataframe(
                t["only_ship"].style.format({"ยอดเงิน_Shipnity": "{:,.2f}"}),
                use_container_width=True,
                hide_index=True
            )

        with c3:

            st.markdown("#### มีเฉพาะ Express")

            st.dataframe(
                t["only_express"],
                use_container_width=True,
                hide_index=True
            )

        export = pd.concat(
            [
                tables[ch][key].assign(Channel=ch, สถานะ=label)
                for ch in CN_CHANNELS
                for key, label in [
                    ("both", "มีทั้ง 2 ระบบ"),
                    ("only_ship", "มีเฉพาะ Shipnity"),
                    ("only_express", "มีเฉพาะ Express"),
                ]
            ],
            ignore_index=True
        )

        st.download_button(
            "⬇️ ดาวน์โหลดรายการทั้งหมด (CSV)",
            data=export.to_csv(index=False).encode("utf-8-sig"),
            file_name="cn_compare.csv",
            mime="text/csv"
        )

    # -----------------------------------------------------
    # TAB : ข้อมูลต้นฉบับ
    # -----------------------------------------------------

    with tab_c:

        st.markdown("### Shipnity (หลังแบ่ง Channel)")

        st.dataframe(
            result["ship"],
            use_container_width=True,
            hide_index=True,
            height=320
        )

        st.markdown("### ข้อมูลที่ดึงจากไฟล์ Express")

        for channel in CN_CHANNELS:

            fc = result["found_codes"][channel]

            with st.expander(
                f"{channel} — พบรหัส {fc['raw']:,} "
                f"(ไม่ซ้ำ {fc['unique']:,})"
            ):

                st.caption(
                    "แถวที่มีคำว่า \"รวม\" "
                    "(ใช้ตัวเลขตัวที่ 4 ของแถวเป็นยอดรวม)"
                )

                st.dataframe(
                    result["totals"][channel],
                    use_container_width=True,
                    hide_index=True
                )


# =========================================================
# Sidebar
# =========================================================

feature = st.sidebar.radio(
    "เลือกฟีเจอร์",
    [
        "📦 ตรวจสอบออเดอร์",
        "↩️ CN (ใบลดหนี้ / รับคืน)"
    ],
    key="feature"
)

st.sidebar.markdown("---")

if feature.startswith("↩️"):

    render_cn_page()

    st.stop()


st.sidebar.markdown(
    "## 📦 Order Dashboard"
)

st.sidebar.caption(
    "ตรวจสอบออเดอร์ • ช่องทาง • ยอดขาย "
    "• ความต่างระหว่างระบบ"
)

st.sidebar.markdown(
    "### 1. อัปโหลดข้อมูล"
)


# =========================================================
# Upload Shipnity
# =========================================================

ship_file = st.sidebar.file_uploader(
    "Shipnity",
    type=["xlsx", "xls"],
    key="ship"
)


# =========================================================
# Upload Category
# =========================================================

cat_file = st.sidebar.file_uploader(
    "Category (ไม่บังคับ)",
    type=["xlsx", "xls"],
    key="cat"
)


# =========================================================
# Upload Report
# =========================================================

report_file = st.sidebar.file_uploader(
    "ใบรายงาน (ไฟล์รายงานเบล)",
    type=["xlsx", "xls"],
    key="report"
)


st.sidebar.markdown("---")


# =========================================================
# Instructions
# =========================================================

st.sidebar.markdown(
    "### วิธีใช้งาน"
)

st.sidebar.caption(
    "① อัปโหลด Shipnity + ใบรายงาน(รายงานเบล dive Y.)\n"
    "② กดประมวลผล\n"
    "③ ดู Dashboard / ตรวจออเดอร์"
)


# =========================================================
# Run
# =========================================================

run = st.sidebar.button(
    "🚀 ประมวลผลข้อมูล",
    type="primary",
    use_container_width=True
)


# =========================================================
# Session State
# =========================================================

if "result" not in st.session_state:

    st.session_state.result = None


# =========================================================
# Process
# =========================================================

if run:

    if not ship_file or not report_file:

        st.sidebar.error(
            "กรุณาอัปโหลดอย่างน้อย Shipnity และใบรายงาน"
        )

    else:

        try:

            with st.spinner(
                "กำลังประมวลผลข้อมูล..."
            ):

                # -----------------------------------------
                # Read Shipnity
                # -----------------------------------------

                ship_raw = read_excel(
                    ship_file
                )

                # -----------------------------------------
                # Read Report
                # -----------------------------------------

                report_raw = read_excel(
                    report_file,
                    sheet_name=-1
                )

                # -----------------------------------------
                # Category
                # -----------------------------------------

                category_info = None

                if cat_file:

                    try:

                        category_info = read_excel(
                            cat_file,
                            sheet_name="Category"
                        )

                    except Exception:

                        category_info = read_excel(
                            cat_file
                        )

                # -----------------------------------------
                # Prepare Shipnity
                # -----------------------------------------

                ship, ship_order, ship_channel = (
                    prepare_shipnity(
                        ship_raw
                    )
                )

                # -----------------------------------------
                # Prepare Report
                # -----------------------------------------

                report, report_order, report_channel = (
                    prepare_report(
                        report_raw
                    )
                )

                # -----------------------------------------
                # Build Comparison
                # -----------------------------------------

                result = build_comparison(
                    ship,
                    ship_order,
                    report,
                    report_order
                )

                # -----------------------------------------
                # Save
                # -----------------------------------------

                st.session_state.result = {

                    "ship_raw":
                        ship_raw,

                    "report_raw":
                        report_raw,

                    "category":
                        category_info,

                    "ship":
                        ship,

                    "report":
                        report,

                    "ship_order":
                        ship_order,

                    "report_order":
                        report_order,

                    "result":
                        result,
                }

            st.sidebar.success(
                "ประมวลผลสำเร็จ"
            )

        except Exception as e:

            st.sidebar.error(
                f"ประมวลผลไม่สำเร็จ: {e}"
            )


# =========================================================
# Initial Page
# =========================================================

if st.session_state.result is None:

    st.title(
        "📦 Order Reconciliation Dashboard"
    )

    st.markdown(
        "#### ตรวจสอบยอด Order ระหว่าง Shinity กับ รายงาน "
    )

    st.markdown(
        """
        <div class="card">

        <h3>เริ่มต้นใช้งาน</h3>

        <p>
        อัปโหลดไฟล์ <b>Shipnity</b>
        และ <b>ใบรายงาน</b>
        ทางด้านซ้าย
        แล้วกด
        <b>🚀 ประมวลผลข้อมูล</b>
        </p>

        <p class="small">
        ระบบจะตรวจสอบออเดอร์
        ยอดขาย
        และ Channel
        ระหว่างสองแหล่งข้อมูล
        </p>

        </div>
        """,
        unsafe_allow_html=True
    )   

    st.info(
        "รองรับ Excel .xlsx / .xls"
    )

    st.stop()


# =========================================================
# Load Result
# =========================================================

data = st.session_state.result

ship = data["ship"]

report = data["report"]

(
    compare,
    s,
    r,
    only_ship,
    only_report,
    both,
    different,
    same
) = data["result"]


# =========================================================
# Overall Metrics
# =========================================================

# รวมเลขออเดอร์จากทั้ง Shipnity และใบรายงาน
# เพื่อไม่ให้ออเดอร์เฉพาะใบรายงานหายไปจากจำนวนรวม

all_order_numbers = (
    compare["เลขที่ออเดอร์"]
    .combine_first(
        compare["order_number"]
    )
)

total_orders = (
    all_order_numbers
    .nunique()
)


# ---------------------------------------------------------
# Shipnity Sales
# ---------------------------------------------------------

ship_sales = (
    s["ยอดขาย_Shipnity"]
    .fillna(0)
    .sum()
)


# ---------------------------------------------------------
# Report Sales
# ---------------------------------------------------------

report_sales = (
    r["ยอดขาย_ใบรายงาน"]
    .fillna(0)
    .sum()
)


# ---------------------------------------------------------
# Difference
# ---------------------------------------------------------

sales_diff = (
    report_sales
    -
    ship_sales
)


# =========================================================
# Main Header
# =========================================================

st.title(
    "📦 Order Reconciliation Dashboard"
)

st.caption(
    "ภาพรวมข้อมูลออเดอร์และการตรวจสอบยอดขาย "
    "ระหว่าง Shipnity กับใบรายงาน"
)


# =========================================================
# Tabs
# =========================================================

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "📊 ภาพรวม",
        "📣 Channel",
        "🔎 ตรวจสอบออเดอร์",
        "📄 ข้อมูลต้นฉบับ"
    ]
)


# =========================================================
# TAB 1 : Overview
# =========================================================

with tab1:

    st.subheader(
        "ภาพรวม"
    )

    ship_orders = s["เลขที่ออเดอร์"].nunique()
    report_orders = r["order_number"].nunique()

    # -----------------------------------------------------
    # 1) จำนวนออเดอร์ + ยอดขาย
    # -----------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric("ออเดอร์ Shipnity", f"{ship_orders:,}")
    c2.metric("ออเดอร์ใบรายงาน", f"{report_orders:,}")
    c3.metric("ออเดอร์หลังรวม", f"{total_orders:,}")

    c4, c5, c6 = st.columns(3)

    c4.metric("ยอดขาย Shipnity", money(ship_sales))
    c5.metric("ยอดขายใบรายงาน", money(report_sales))
    c6.metric(
        "ส่วนต่างรวม (ใบรายงาน − Shipnity)",
        money(sales_diff)
    )

    # -----------------------------------------------------
    # 2) สรุปแหล่งที่มาของออเดอร์ (เหมือน summary_order ใน Notebook)
    # -----------------------------------------------------

    st.markdown("### สถานะการจับคู่")

    status_keys = [
        "มีทั้ง Shipnity และใบรายงาน",
        "มีเฉพาะ Shipnity",
        "มีเฉพาะใบรายงาน",
    ]

    status_labels = {
        "มีทั้ง Shipnity และใบรายงาน": "มีทั้ง 2 ไฟล์",
        "มีเฉพาะ Shipnity": "ต่าง Shipnity (มีเฉพาะ Shipnity)",
        "มีเฉพาะใบรายงาน": "ต่างใบรายงาน (มีเฉพาะใบรายงาน)",
    }

    summary_order = (
        compare
        .groupby("_merge")
        .agg(
            **{
                "จำนวนออเดอร์": ("ส่วนต่างยอดขาย", "size"),
                "ยอดขาย_Shipnity": ("ยอดขาย_Shipnity", "sum"),
                "ยอดขาย_ใบรายงาน": ("ยอดขาย_ใบรายงาน", "sum"),
                "ส่วนต่างยอดขาย": ("ส่วนต่างยอดขาย", "sum"),
            }
        )
        .reindex(status_keys, fill_value=0)
        .rename_axis("สถานะ")
        .reset_index()
    )

    summary_order["สถานะ"] = summary_order["สถานะ"].map(status_labels)

    summary_order = summary_order.rename(
        columns={
            "ยอดขาย_Shipnity": "ยอดขาย Shipnity",
            "ยอดขาย_ใบรายงาน": "ยอดขายใบรายงาน",
            "ส่วนต่างยอดขาย": "ผลต่างยอดเงิน",
        }
    )

    a_col, b_col = st.columns([1, 1])

    with a_col:

        fig = px.pie(
            summary_order,
            names="สถานะ",
            values="จำนวนออเดอร์",
            hole=.55
        )

        fig.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
            legend_title=""
        )

        st.plotly_chart(fig, use_container_width=True)

    with b_col:

        status_table = pd.concat(
            [
                summary_order,
                pd.DataFrame(
                    [
                        {
                            "สถานะ": "รวม",
                            "จำนวนออเดอร์":
                                summary_order["จำนวนออเดอร์"].sum(),
                            "ยอดขาย Shipnity":
                                summary_order["ยอดขาย Shipnity"].sum(),
                            "ยอดขายใบรายงาน":
                                summary_order["ยอดขายใบรายงาน"].sum(),
                            "ผลต่างยอดเงิน":
                                summary_order["ผลต่างยอดเงิน"].sum(),
                        }
                    ]
                ),
            ],
            ignore_index=True
        )

        st.dataframe(
            status_table.style.format(
                {
                    "จำนวนออเดอร์": "{:,.0f}",
                    "ยอดขาย Shipnity": "{:,.2f}",
                    "ยอดขายใบรายงาน": "{:,.2f}",
                    "ผลต่างยอดเงิน": "{:,.2f}",
                }
            ),
            use_container_width=True,
            hide_index=True
        )

    st.caption(
        "ผลต่างยอดเงินในตารางนี้ = ยอดขาย Shipnity − ยอดขายใบรายงาน "
        "(ลบ = ใบรายงานมากกว่า)"
    )

    # -----------------------------------------------------
    # 3) ตรวจสอบยอดขายของออเดอร์ที่มีทั้ง 2 แหล่ง
    # -----------------------------------------------------

    st.markdown("### ตรวจสอบยอดขายของออเดอร์ที่มีทั้ง 2 แหล่ง")

    both_ship_sales = both["ยอดขาย_Shipnity"].fillna(0).sum()
    both_report_sales = both["ยอดขาย_ใบรายงาน"].fillna(0).sum()

    d1, d2, d3, d4 = st.columns(4)

    d1.metric("ออเดอร์ที่มีทั้ง 2 ไฟล์", f"{len(both):,}")
    d2.metric("ยอดขายตรงกัน", f"{len(same):,}")
    d3.metric("ยอดขายไม่ตรงกัน", f"{len(different):,}")
    d4.metric(
        "ส่วนต่างรวม (ยอดไม่ตรง)",
        money(different["ส่วนต่างยอดขาย"].sum())
    )

    st.caption(
        f"ยอดขายของออเดอร์ที่มีทั้ง 2 ไฟล์ — "
        f"Shipnity {both_ship_sales:,.2f} | "
        f"ใบรายงาน {both_report_sales:,.2f} | "
        f"ส่วนต่าง {both_ship_sales - both_report_sales:,.2f} บาท"
    )

    # -----------------------------------------------------
    # 4) ตรวจสอบส่วนต่างยอดขายทั้งหมด (เหมือน Notebook ข้อ [1]-[6])
    # -----------------------------------------------------

    st.markdown("### ตรวจสอบส่วนต่างยอดขายทั้งหมด")

    only_ship_sales = only_ship["ยอดขาย_Shipnity"].fillna(0).sum()
    only_report_sales = only_report["ยอดขาย_ใบรายงาน"].fillna(0).sum()

    check_ship = both_ship_sales + only_ship_sales
    check_report = both_report_sales + only_report_sales

    recon = pd.DataFrame(
        {
            "รายการ": [
                "[1] ยอดขายทั้งหมด",
                "[2] ออเดอร์ที่มีทั้ง 2 ไฟล์",
                "[3] ต่าง Shipnity (มีเฉพาะ Shipnity)",
                "[4] ต่างใบรายงาน (มีเฉพาะใบรายงาน)",
                "[5] รวม [2]+[3]+[4]",
            ],
            "จำนวนออเดอร์": [
                total_orders,
                len(both),
                len(only_ship),
                len(only_report),
                len(both) + len(only_ship) + len(only_report),
            ],
            "ยอดขาย Shipnity": [
                ship_sales,
                both_ship_sales,
                only_ship_sales,
                0,
                check_ship,
            ],
            "ยอดขายใบรายงาน": [
                report_sales,
                both_report_sales,
                0,
                only_report_sales,
                check_report,
            ],
        }
    )

    st.dataframe(
        recon.style.format(
            {
                "จำนวนออเดอร์": "{:,.0f}",
                "ยอดขาย Shipnity": "{:,.2f}",
                "ยอดขายใบรายงาน": "{:,.2f}",
            }
        ),
        use_container_width=True,
        hide_index=True
    )

    st.metric(
        "[6] ส่วนต่างยอดขายรวม (ใบรายงาน − Shipnity)",
        money(report_sales - ship_sales)
    )

    if (
        abs(check_ship - ship_sales) > 0.01
        or abs(check_report - report_sales) > 0.01
    ):
        st.warning(
            "ยอดรวม [5] ไม่ตรงกับ [1] — ตรวจสอบเลขออเดอร์ที่ว่างหรือซ้ำ"
        )


with tab2:

    st.subheader("Channel Performance")

    # =====================================================
    # 1. สรุปจำนวนออเดอร์จาก Shipnity
    #
    # s = ข้อมูล Shipnity ที่ถูก Group เป็น 1 แถวต่อ 1 ออเดอร์
    # =====================================================

    ship_channel_count = (
        s
        .groupby(
            "Channel_Category_Shipnity",
            dropna=False
        )
        .size()
        .reset_index(
            name="จำนวนออเดอร์_Shipnity"
        )
        .rename(
            columns={
                "Channel_Category_Shipnity":
                    "Channel"
            }
        )
    )

    # =====================================================
    # 2. สรุปยอดขายจาก Shipnity
    # =====================================================

    ship_channel_sales = (
        s
        .groupby(
            "Channel_Category_Shipnity",
            dropna=False
        )["ยอดขาย_Shipnity"]
        .sum()
        .reset_index()
        .rename(
            columns={
                "Channel_Category_Shipnity":
                    "Channel"
            }
        )
    )

    # =====================================================
    # 3. รวมจำนวน + ยอดขาย Shipnity
    # =====================================================

    ship_channel_summary = pd.merge(
        ship_channel_count,
        ship_channel_sales,
        on="Channel",
        how="outer"
    )

    # =====================================================
    # 4. ทำความสะอาด Channel
    # =====================================================

    ship_channel_summary["Channel"] = (
        ship_channel_summary["Channel"]
        .fillna("ไม่ระบุ")
        .astype(str)
        .str.strip()
    )

    # =====================================================
    # 5. หาเฉพาะออเดอร์จากใบรายงาน
    #
    # ตัวอย่าง:
    #
    # MM261006-515
    # 449.99
    # Online Marketing
    #
    # จะถูกนับตรงนี้
    # =====================================================

    if not only_report.empty:

        # -----------------------------------------------
        # Clean Channel
        # -----------------------------------------------

        only_report["Channel_Category_ใบรายงาน"] = (
            only_report[
                "Channel_Category_ใบรายงาน"
            ]
            .fillna("ไม่ระบุ")
            .astype(str)
            .str.strip()
        )

        # -----------------------------------------------
        # จำนวนออเดอร์เฉพาะใบรายงาน
        # -----------------------------------------------

        report_only_count = (
            only_report
            .groupby(
                "Channel_Category_ใบรายงาน",
                dropna=False
            )
            .size()
        )

        # -----------------------------------------------
        # ยอดขายเฉพาะใบรายงาน
        # -----------------------------------------------

        report_only_sales = (
            only_report
            .groupby(
                "Channel_Category_ใบรายงาน",
                dropna=False
            )[
                "ยอดขาย_ใบรายงาน"
            ]
            .sum()
        )

    else:

        report_only_count = pd.Series(
            dtype="float64"
        )

        report_only_sales = pd.Series(
            dtype="float64"
        )

    # =====================================================
    # 6. เอาจำนวนใบรายงานมา MAP เข้า Channel
    #
    # จุดสำคัญ:
    #
    # Online Marketing
    # Shipnity = 601
    # ใบรายงาน = 1
    #
    # จะกลายเป็น 602
    # =====================================================

    channel_summary = ship_channel_summary.copy()

    channel_summary[
        "จำนวนออเดอร์_ใบรายงาน"
    ] = (
        channel_summary["Channel"]
        .map(report_only_count)
        .fillna(0)
    )

    # =====================================================
    # 7. เอายอดขายใบรายงานมา MAP เข้า Channel
    # =====================================================

    channel_summary[
        "ยอดขาย_ใบรายงาน"
    ] = (
        channel_summary["Channel"]
        .map(report_only_sales)
        .fillna(0)
    )

    # =====================================================
    # 8. รวมจำนวนออเดอร์
    # =====================================================

    channel_summary[
        "จำนวนออเดอร์"
    ] = (
        channel_summary[
            "จำนวนออเดอร์_Shipnity"
        ]
        +
        channel_summary[
            "จำนวนออเดอร์_ใบรายงาน"
        ]
    )

    # =====================================================
    # 9. รวมยอดขาย
    # =====================================================

    channel_summary[
        "ยอดขาย"
    ] = (
        channel_summary[
            "ยอดขาย_Shipnity"
        ]
        +
        channel_summary[
            "ยอดขาย_ใบรายงาน"
        ]
    )

    # =====================================================
    # 10. บังคับให้เป็นตัวเลข
    # =====================================================

    channel_summary[
        "จำนวนออเดอร์"
    ] = pd.to_numeric(
        channel_summary[
            "จำนวนออเดอร์"
        ],
        errors="coerce"
    ).fillna(0)

    channel_summary[
        "ยอดขาย"
    ] = pd.to_numeric(
        channel_summary[
            "ยอดขาย"
        ],
        errors="coerce"
    ).fillna(0)

    # =====================================================
    # 11. จัดลำดับ Channel
    # =====================================================

    channel_order = [
        "Call Center",
        "Online Marketing",
        "ไม่ระบุ"
    ]

    channel_summary["Channel"] = pd.Categorical(
        channel_summary["Channel"],
        categories=channel_order,
        ordered=True
    )

    channel_summary = (
        channel_summary
        .sort_values("Channel")
        .reset_index(drop=True)
    )

    # =====================================================
    # 12. กราฟจำนวนออเดอร์
    # =====================================================

    col1, col2 = st.columns(2)

    with col1:

        fig_order = px.bar(
            channel_summary,
            x="Channel",
            y="จำนวนออเดอร์",
            text="จำนวนออเดอร์",
            title="จำนวนออเดอร์แยกตาม Channel"
        )

        fig_order.update_traces(
            texttemplate="%{text:,.0f}",
            textposition="inside"
        )

        fig_order.update_layout(
            xaxis_title="",
            yaxis_title="ออเดอร์",
            showlegend=False
        )

        st.plotly_chart(
            fig_order,
            use_container_width=True
        )

    # =====================================================
    # 13. กราฟยอดขาย
    # =====================================================

    with col2:

        fig_sales = px.bar(
            channel_summary,
            x="Channel",
            y="ยอดขาย",
            text="ยอดขาย",
            title="ยอดขายแยกตาม Channel"
        )

        fig_sales.update_traces(
            texttemplate="%{text:,.2s}",
            textposition="inside"
        )

        fig_sales.update_layout(
            xaxis_title="",
            yaxis_title="บาท",
            showlegend=False
        )

        st.plotly_chart(
            fig_sales,
            use_container_width=True
        )

    # =====================================================
    # 14. ตารางสรุปสุดท้าย
    # =====================================================

    st.markdown(
        "### สรุป Channel"
    )

    final_channel_table = channel_summary[
        [
            "Channel",
            "จำนวนออเดอร์",
            "ยอดขาย"
        ]
    ].copy()

    total_row = pd.DataFrame({
        "Channel": ["รวมทั้งหมด"],
        "จำนวนออเดอร์": [
            final_channel_table["จำนวนออเดอร์"].sum()
        ],
        "ยอดขาย": [
            final_channel_table["ยอดขาย"].sum()
        ]
    })

    final_channel_table = pd.concat(
        [
            final_channel_table,
            total_row
        ],
        ignore_index=True
    )

    # =====================================================
    # แสดงตาราง
    # =====================================================

    st.dataframe(
        final_channel_table.style.format(
            {
                "จำนวนออเดอร์": "{:,.0f}",
                "ยอดขาย": "{:,.2f}"
            }
        ),
        use_container_width=True,
        hide_index=True
    )

# =========================================================
# TAB 3 : Reconciliation
# =========================================================

with tab3:

    st.subheader(
        "🔎 ตรวจสอบออเดอร์"
    )

    st.caption(
        "เลือกมุมมองที่ต้องการ "
        "แล้วค้นหาเลขที่ออเดอร์ได้ทันที"
    )

    # =====================================================
    # View
    # =====================================================

    view = st.radio(
        "มุมมอง",
        [
            "ทั้งหมด",
            "มีเฉพาะ Shipnity",
            "มีเฉพาะใบรายงาน",
            "มีทั้ง 2 แหล่ง",
            "ยอดขายไม่ตรงกัน",
            "ยอดขายตรงกัน"
        ],
        horizontal=True
    )

    # =====================================================
    # Search
    # =====================================================

    search = st.text_input(
        "🔍 ค้นหาเลขที่ออเดอร์",
        placeholder="เช่น MM261007-301"
    )

    # =====================================================
    # Select Table
    # =====================================================

    if view == "มีเฉพาะ Shipnity":

        table = only_ship.copy()

    elif view == "มีเฉพาะใบรายงาน":

        table = only_report.copy()

    elif view == "มีทั้ง 2 แหล่ง":

        table = both.copy()

    elif view == "ยอดขายไม่ตรงกัน":

        table = different.copy()

    elif view == "ยอดขายตรงกัน":

        table = same.copy()

    else:

        table = compare.copy()

    # =====================================================
    # Search
    # =====================================================

    if search.strip():

        mask_left = (
            table["เลขที่ออเดอร์"]
            .astype(str)
            .str.contains(
                search.strip(),
                case=False,
                na=False
            )
        )

        if "order_number" in table.columns:

            mask_right = (
                table["order_number"]
                .astype(str)
                .str.contains(
                    search.strip(),
                    case=False,
                    na=False
                )
            )

        else:

            mask_right = False

        table = table[
            mask_left | mask_right
        ]

    # =====================================================
    # Columns
    # =====================================================

    cols = [
        "เลขที่ออเดอร์",
        "order_number",
        "ยอดขาย_Shipnity",
        "ยอดขาย_ใบรายงาน",
        "ส่วนต่างยอดขาย",
        "_merge"
    ]

    cols = [
        c for c in cols
        if c in table.columns
    ]

    st.write(
        f"พบ **{len(table):,}** รายการ"
    )

    # =====================================================
    # Display
    # =====================================================

    st.dataframe(
        table[cols].style.format(
            {
                "ยอดขาย_Shipnity":
                    "{:,.2f}",

                "ยอดขาย_ใบรายงาน":
                    "{:,.2f}",

                "ส่วนต่างยอดขาย":
                    "{:,.2f}",
            }
        ),
        use_container_width=True,
        height=520,
        hide_index=True
    )

    # =====================================================
    # CSV
    # =====================================================

    csv = table.to_csv(
        index=False
    ).encode(
        "utf-8-sig"
    )

    st.download_button(
        "⬇️ ดาวน์โหลดผลลัพธ์ที่กำลังดูเป็น CSV",
        data=csv,
        file_name="order_reconciliation_result.csv",
        mime="text/csv"
    )


# =========================================================
# TAB 4 : Raw Data
# =========================================================

with tab4:

    st.subheader(
        "📄 ข้อมูลต้นฉบับ"
    )

    raw_source = st.selectbox(
        "เลือกแหล่งข้อมูล",
        [
            "Shipnity",
            "ใบรายงาน"
        ]
    )

    if raw_source == "Shipnity":

        raw = data[
            "ship_raw"
        ]

    else:

        raw = data[
            "report_raw"
        ]

    st.caption(
        f"{len(raw):,} แถว × "
        f"{len(raw.columns):,} คอลัมน์"
    )

    st.dataframe(
        raw,
        use_container_width=True,
        height=600
    )