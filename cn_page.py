"""หน้า CN: ใบลดหนี้ / รับคืนสินค้า (Shipnity vs Express)

โครงหน้า (บนลงล่าง):
    page_header        หัวหน้า
    _upload_card       อัปโหลด 3 ไฟล์ + ปุ่มประมวลผล
    _results_panel     (ซ้าย) KPI 3 ใบ + ตัวกรอง + ตารางพร้อมป้ายสถานะ
    _summary_panel     (ขวา) สรุปภาพรวม + กราฟ
    st.tabs            รายละเอียดเพิ่มเติม: _tab_summary / _tab_raw
"""

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from cn_logic import CN_CHANNELS, build_cn_result, read_express_lines
from ui import (
    card,
    chip,
    esc,
    file_chips,
    fmt_money,
    html_table,
    kpi_cards,
    md,
    page_controls,
    page_slice,
    section_title,
    stat_rows,
)
from utils import money, read_excel


def _tab_summary(result):

    summary = result["summary"]

    total_row = summary[summary["Channel"] == "รวม"].iloc[0]

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

    m4.metric("ยอดเงิน Shipnity", money(total_row["ยอดเงิน_Shipnity"]))

    m5.metric("ยอดเงิน Express", money(total_row["ยอดเงิน_Express"]))

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


def _tab_raw(result):

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
# Upload card
# =========================================================

def _upload_card():

    with card("cn_upload"):

        section_title("อัปโหลดไฟล์")

        c1, c2, c3, c4 = st.columns([3, 3, 3, 2], vertical_alignment="bottom")

        with c1:
            ship_file = st.file_uploader(
                "Shipnity (รายการรับคืน)",
                type=["xlsx", "xls"],
                key="cn_ship"
            )

        with c2:
            online_file = st.file_uploader(
                "Express - Online",
                type=["csv", "txt"],
                key="cn_online"
            )

        with c3:
            call_file = st.file_uploader(
                "Express - Call Center",
                type=["csv", "txt"],
                key="cn_call"
            )

        with c4:
            run = st.button(
                "🚀 ประมวลผล CN",
                type="primary",
                use_container_width=True,
                key="cn_run"
            )

        file_chips(
            [
                ("Shipnity", bool(ship_file)),
                ("Express Online", bool(online_file)),
                ("Express Call Center", bool(call_file)),
            ]
        )

    return ship_file, online_file, call_file, run


# =========================================================
# Process
# =========================================================

def _process(ship_file, online_file, call_file):

    if not (ship_file and online_file and call_file):

        st.error("กรุณาอัปโหลดให้ครบทั้ง 3 ไฟล์")

        return

    try:

        with st.spinner("กำลังประมวลผลข้อมูล..."):

            ship_raw = read_excel(ship_file)

            online_lines = read_express_lines(online_file)
            call_lines = read_express_lines(call_file)

            result = build_cn_result(
                ship_raw,
                online_lines,
                call_lines
            )

            result["ship_raw"] = ship_raw

        st.session_state.cn_result = result

        st.session_state.last_run = datetime.now()

        st.success("ประมวลผลสำเร็จ")

    except Exception as e:

        st.error(f"ประมวลผลไม่สำเร็จ: {e}")


def _initial_page():

    md(
        '<div class="card">'
        '<h3>เริ่มต้นใช้งาน</h3>'
        '<p>อัปโหลดไฟล์ <b>Shipnity</b>, <b>Express Online</b> และ '
        '<b>Express Call Center</b> ด้านบน แล้วกด <b>🚀 ประมวลผล CN</b></p>'
        '<p class="small">ระบบจะแบ่ง Channel ของ Shipnity '
        'ดึงเลขที่ออเดอร์และยอดรวมจากไฟล์ Express '
        'แล้วเปรียบเทียบจำนวนรายการ ยอดเงิน และรหัสที่ต่างกัน</p>'
        '</div>'
    )


# =========================================================
# ผลการตรวจสอบ (ซ้าย)
# =========================================================

# key ใน result["tables"][channel] → (ป้ายสถานะ, สี)
STATUS = {
    "only_express": ("มีเฉพาะ Express", "red"),
    "only_ship": ("มีเฉพาะ Shipnity", "amber"),
    "both": ("มีทั้ง 2 ระบบ", "green"),
}

STATUS_FILTERS = ["ทั้งหมด"] + [label for label, _ in STATUS.values()]


def _channel_rows(tables):
    """รวม 3 ตารางของ Channel เป็นตารางเดียว (เรียงรายการผิดปกติขึ้นก่อน)"""

    frames = []

    for key in STATUS:

        t = tables[key].copy()

        if t.empty:
            continue

        if "ยอดเงิน_Shipnity" not in t.columns:
            t["ยอดเงิน_Shipnity"] = float("nan")

        t["_key"] = key

        frames.append(t[["รหัส", "ยอดเงิน_Shipnity", "_key"]])

    if not frames:

        return pd.DataFrame(columns=["รหัส", "ยอดเงิน_Shipnity", "_key"])

    return pd.concat(frames, ignore_index=True)


CN_TABLE_COLS = [
    ("ลำดับ", lambda r, n: str(n), "c"),
    ("เลขที่ออเดอร์", lambda r, n: f'<b>{esc(r["รหัส"])}</b>', "l"),
    ("ยอดเงิน Shipnity", lambda r, n: fmt_money(r["ยอดเงิน_Shipnity"]), "r"),
    (
        "สถานะ",
        lambda r, n: chip(*STATUS[r["_key"]]),
        "l"
    ),
]


def _results_panel(result):

    tables = result["tables"]

    with card("cn_results"):

        section_title(
            "ผลการตรวจสอบ",
            "เปรียบเทียบรหัสออเดอร์ระหว่าง Shipnity กับ Express"
        )

        for channel in CN_CHANNELS:

            if result["totals"][channel].empty:

                st.warning(
                    f"{channel}: ไม่พบแถว \"รวม\" ในไฟล์ Express "
                    "จึงนับยอดเงิน Express เป็น 0"
                )

        channel = st.radio(
            "Channel",
            CN_CHANNELS,
            horizontal=True,
            key="cn_channel"
        )

        t = tables[channel]

        total = len(t["both"]) + len(t["only_ship"]) + len(t["only_express"])

        kpi_cards(
            [
                {
                    "label": "มีทั้ง 2 ระบบ",
                    "count": len(t["both"]),
                    "total": total,
                    "tone": "green",
                },
                {
                    "label": "มีเฉพาะ Shipnity",
                    "count": len(t["only_ship"]),
                    "total": total,
                    "tone": "amber",
                },
                {
                    "label": "มีเฉพาะ Express",
                    "count": len(t["only_express"]),
                    "total": total,
                    "tone": "red",
                },
            ]
        )

        f1, f2, f3 = st.columns([3, 4, 3], vertical_alignment="bottom")

        with f1:
            status = st.selectbox(
                "สถานะ",
                STATUS_FILTERS,
                key="cn_status"
            )

        with f2:
            search = st.text_input(
                "🔍 ค้นหาเลขที่ออเดอร์",
                placeholder="เช่น MM261007-301",
                key="cn_search"
            )

        rows = _channel_rows(t)

        if status != "ทั้งหมด":

            keep = [k for k, (label, _) in STATUS.items() if label == status]

            rows = rows[rows["_key"].isin(keep)]

        if search.strip():

            rows = rows[
                rows["รหัส"]
                .astype(str)
                .str.contains(
                    search.strip(),
                    case=False,
                    na=False,
                    regex=False
                )
            ]

        # ไฟล์ดาวน์โหลด = ทุก Channel ทุกสถานะ (เหมือนเดิม)

        export = pd.concat(
            [
                tables[ch][key].assign(Channel=ch, สถานะ=label)
                for ch in CN_CHANNELS
                for key, (label, _) in STATUS.items()
            ],
            ignore_index=True
        )

        with f3:
            st.download_button(
                "⬇️ ดาวน์โหลด CSV",
                data=export.to_csv(index=False).encode("utf-8-sig"),
                file_name="cn_compare.csv",
                mime="text/csv",
                use_container_width=True
            )

        st.caption(f"พบ {len(rows):,} รายการ")

        page_df, start = page_slice(rows, "cn_tbl")

        html_table(page_df, CN_TABLE_COLS, start)

        page_controls("cn_tbl", len(rows), start)


# =========================================================
# สรุปภาพรวม (ขวา)
# =========================================================

def _summary_panel(result):

    summary = result["summary"]

    total_row = summary[summary["Channel"] == "รวม"].iloc[0]

    with card("cn_summary"):

        section_title("สรุปภาพรวม")

        stat_rows(
            [
                (
                    "📄",
                    "รายการ Shipnity",
                    f"{total_row['จำนวนรายการ_Shipnity']:,.0f}"
                ),
                (
                    "🧾",
                    "รายการ Express",
                    f"{total_row['จำนวนรายการ_Express']:,.0f}"
                ),
                (
                    "💰",
                    "ยอดเงิน Shipnity",
                    money(total_row["ยอดเงิน_Shipnity"])
                ),
                (
                    "💳",
                    "ยอดเงิน Express",
                    money(total_row["ยอดเงิน_Express"])
                ),
                (
                    "⚖️",
                    "ส่วนต่างยอดเงิน (Shipnity − Express)",
                    money(total_row["ส่วนต่างยอดเงิน"])
                ),
            ]
        )

        st.markdown("**ยอดเงินแยกตาม Channel**")

        fig = px.bar(
            summary[summary["Channel"] != "รวม"],
            x="Channel",
            y=["ยอดเงิน_Shipnity", "ยอดเงิน_Express"],
            barmode="group"
        )

        fig.update_layout(
            height=260,
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", y=-0.2, title=""),
            yaxis_title="ยอดเงิน (บาท)",
            xaxis_title=""
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            key="cn_amount_bar"
        )


# =========================================================
# Entry point
# =========================================================

def render_cn_page():

    if "cn_result" not in st.session_state:
        st.session_state.cn_result = None

    ship_file, online_file, call_file, run = _upload_card()

    if run:
        _process(ship_file, online_file, call_file)

    result = st.session_state.cn_result

    if result is None:
        _initial_page()
        return

    left, right = st.columns([7, 3])

    with left:
        _results_panel(result)

    with right:
        _summary_panel(result)

    section_title("รายละเอียดเพิ่มเติม")

    tab_a, tab_b = st.tabs(
        [
            "📊 สรุปตาม Channel",
            "📄 ข้อมูลต้นฉบับ"
        ]
    )

    with tab_a:
        _tab_summary(result)

    with tab_b:
        _tab_raw(result)
