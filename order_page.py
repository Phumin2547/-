"""หน้า "ตรวจสอบออเดอร์" (Shipnity vs ใบรายงาน)

โครงหน้า (บนลงล่าง):
    page_header        หัวหน้า
    _upload_card       อัปโหลดไฟล์ + ปุ่มประมวลผล
    _results_panel     (ซ้าย) KPI 3 ใบ + ตัวกรอง + ตารางพร้อมป้ายสถานะ
    _summary_panel     (ขวา) สรุปภาพรวม + กราฟสัดส่วน
    st.tabs            รายละเอียดเพิ่มเติม: _tab_overview / _tab_channel / _tab_raw
"""

from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import plotly.express as px
import streamlit as st

from order_logic import (
    STATUS_BOTH,
    STATUS_ONLY_SHIP,
    EXPRESS_CHANNELS,
    build_comparison,
    build_express_totals,
    prepare_report,
    prepare_shipnity,
)
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


def _load_context():

    data = st.session_state.result

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

    # รวมเลขออเดอร์จากทั้ง Shipnity และใบรายงาน
    # เพื่อไม่ให้ออเดอร์เฉพาะใบรายงานหายไปจากจำนวนรวม
    all_order_numbers = compare["เลขที่ออเดอร์"].combine_first(
        compare["order_number"]
    )

    total_orders = all_order_numbers.nunique()

    ship_sales = s["ยอดขาย_Shipnity"].fillna(0).sum()

    report_sales = r["ยอดขาย_ใบรายงาน"].fillna(0).sum()

    return SimpleNamespace(
        data=data,
        compare=compare,
        s=s,
        r=r,
        only_ship=only_ship,
        only_report=only_report,
        both=both,
        different=different,
        same=same,
        total_orders=total_orders,
        ship_sales=ship_sales,
        report_sales=report_sales,
        sales_diff=report_sales - ship_sales,
    )


def _tab_overview(c):

    st.subheader("ภาพรวม")

    ship_orders = c.s["เลขที่ออเดอร์"].nunique()
    report_orders = c.r["order_number"].nunique()

    # ---- 1) จำนวนออเดอร์ + ยอดขาย ----

    c1, c2, c3 = st.columns(3)

    c1.metric("ออเดอร์ Shipnity", f"{ship_orders:,}")
    c2.metric("ออเดอร์ใบรายงาน", f"{report_orders:,}")
    c3.metric("ออเดอร์หลังรวม", f"{c.total_orders:,}")

    c4, c5, c6 = st.columns(3)

    c4.metric("ยอดขาย Shipnity", money(c.ship_sales))
    c5.metric("ยอดขายใบรายงาน", money(c.report_sales))
    c6.metric(
        "ส่วนต่างรวม (ใบรายงาน − Shipnity)",
        money(c.sales_diff)
    )

    # ---- 2) สถานะการจับคู่ ----

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
        c.compare
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

    # ---- 3) ออเดอร์ที่มีทั้ง 2 แหล่ง ----

    st.markdown("### ตรวจสอบยอดขายของออเดอร์ที่มีทั้ง 2 แหล่ง")

    both_ship_sales = c.both["ยอดขาย_Shipnity"].fillna(0).sum()
    both_report_sales = c.both["ยอดขาย_ใบรายงาน"].fillna(0).sum()

    d1, d2, d3, d4 = st.columns(4)

    d1.metric("ออเดอร์ที่มีทั้ง 2 ไฟล์", f"{len(c.both):,}")
    d2.metric("ยอดขายตรงกัน", f"{len(c.same):,}")
    d3.metric("ยอดขายไม่ตรงกัน", f"{len(c.different):,}")
    d4.metric(
        "ส่วนต่างรวม (ยอดไม่ตรง)",
        money(c.different["ส่วนต่างยอดขาย"].sum())
    )

    st.caption(
        f"ยอดขายของออเดอร์ที่มีทั้ง 2 ไฟล์ — "
        f"Shipnity {both_ship_sales:,.2f} | "
        f"ใบรายงาน {both_report_sales:,.2f} | "
        f"ส่วนต่าง {both_ship_sales - both_report_sales:,.2f} บาท"
    )

    # ---- 4) ตรวจสอบส่วนต่างยอดขายทั้งหมด ----

    st.markdown("### ตรวจสอบส่วนต่างยอดขายทั้งหมด")

    only_ship_sales = c.only_ship["ยอดขาย_Shipnity"].fillna(0).sum()
    only_report_sales = c.only_report["ยอดขาย_ใบรายงาน"].fillna(0).sum()

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
                c.total_orders,
                len(c.both),
                len(c.only_ship),
                len(c.only_report),
                len(c.both) + len(c.only_ship) + len(c.only_report),
            ],
            "ยอดขาย Shipnity": [
                c.ship_sales,
                both_ship_sales,
                only_ship_sales,
                0,
                check_ship,
            ],
            "ยอดขายใบรายงาน": [
                c.report_sales,
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
        money(c.report_sales - c.ship_sales)
    )

    if (
        abs(check_ship - c.ship_sales) > 0.01
        or abs(check_report - c.report_sales) > 0.01
    ):
        st.warning(
            "ยอดรวม [5] ไม่ตรงกับ [1] — ตรวจสอบเลขออเดอร์ที่ว่างหรือซ้ำ"
        )


def _tab_channel(c):

    s = c.s
    only_report = c.only_report

    st.subheader("Channel Performance")

    # ---- 1. จำนวนออเดอร์จาก Shipnity (s = 1 แถว / ออเดอร์) ----

    ship_channel_count = (
        s
        .groupby("Channel_Category_Shipnity", dropna=False)
        .size()
        .reset_index(name="จำนวนออเดอร์_Shipnity")
        .rename(columns={"Channel_Category_Shipnity": "Channel"})
    )

    # ---- 2. ยอดขายจาก Shipnity ----

    ship_channel_sales = (
        s
        .groupby("Channel_Category_Shipnity", dropna=False)["ยอดขาย_Shipnity"]
        .sum()
        .reset_index()
        .rename(columns={"Channel_Category_Shipnity": "Channel"})
    )

    # ---- 3. รวมจำนวน + ยอดขาย Shipnity ----

    ship_channel_summary = pd.merge(
        ship_channel_count,
        ship_channel_sales,
        on="Channel",
        how="outer"
    )

    # ---- 4. ทำความสะอาด Channel ----

    ship_channel_summary["Channel"] = (
        ship_channel_summary["Channel"]
        .fillna("ไม่ระบุ")
        .astype(str)
        .str.strip()
    )

    # ---- 5. ออเดอร์ที่มีเฉพาะใบรายงาน ----

    if not only_report.empty:

        only_report = only_report.copy()

        only_report["Channel_Category_ใบรายงาน"] = (
            only_report["Channel_Category_ใบรายงาน"]
            .fillna("ไม่ระบุ")
            .astype(str)
            .str.strip()
        )

        report_only_count = (
            only_report
            .groupby("Channel_Category_ใบรายงาน", dropna=False)
            .size()
        )

        report_only_sales = (
            only_report
            .groupby("Channel_Category_ใบรายงาน", dropna=False)["ยอดขาย_ใบรายงาน"]
            .sum()
        )

    else:

        report_only_count = pd.Series(dtype="float64")
        report_only_sales = pd.Series(dtype="float64")

    # ---- 6-7. map ใบรายงานเข้า Channel ----
    # เช่น Online Marketing: Shipnity 601 + ใบรายงาน 1 = 602

    channel_summary = ship_channel_summary.copy()

    channel_summary["จำนวนออเดอร์_ใบรายงาน"] = (
        channel_summary["Channel"].map(report_only_count).fillna(0)
    )

    channel_summary["ยอดขาย_ใบรายงาน"] = (
        channel_summary["Channel"].map(report_only_sales).fillna(0)
    )

    # ---- 8-9. รวมจำนวน / ยอดขาย ----

    channel_summary["จำนวนออเดอร์"] = (
        channel_summary["จำนวนออเดอร์_Shipnity"]
        + channel_summary["จำนวนออเดอร์_ใบรายงาน"]
    )

    channel_summary["ยอดขาย"] = (
        channel_summary["ยอดขาย_Shipnity"]
        + channel_summary["ยอดขาย_ใบรายงาน"]
    )

    # ---- 10. บังคับให้เป็นตัวเลข ----

    channel_summary["จำนวนออเดอร์"] = pd.to_numeric(
        channel_summary["จำนวนออเดอร์"],
        errors="coerce"
    ).fillna(0)

    channel_summary["ยอดขาย"] = pd.to_numeric(
        channel_summary["ยอดขาย"],
        errors="coerce"
    ).fillna(0)

    # ---- 11. จัดลำดับ Channel ----

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

    # ---- 12. กราฟจำนวนออเดอร์ ----

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

        st.plotly_chart(fig_order, use_container_width=True)

    # ---- 13. กราฟยอดขาย ----

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

        st.plotly_chart(fig_sales, use_container_width=True)

    # ---- 14. ตารางสรุปสุดท้าย ----

    st.markdown("### สรุป Channel")

    final_channel_table = channel_summary[
        ["Channel", "จำนวนออเดอร์", "ยอดขาย"]
    ].copy()

    total_row = pd.DataFrame(
        {
            "Channel": ["รวมทั้งหมด"],
            "จำนวนออเดอร์": [final_channel_table["จำนวนออเดอร์"].sum()],
            "ยอดขาย": [final_channel_table["ยอดขาย"].sum()],
        }
    )

    final_channel_table = pd.concat(
        [final_channel_table, total_row],
        ignore_index=True
    )

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

    _express_compare(c, channel_summary)


def _express_compare(c, channel_summary):
    """ตารางเปรียบเทียบยอดเงินกับไฟล์ Express แต่ละประเภท
    (ยอดฝั่ง Express ดึงแบบเดียวกับหน้า CN)"""

    express = c.data.get("express") or {}

    st.markdown("### เปรียบเทียบยอดเงิน Express")

    if all(express.get(ch) is None for ch in EXPRESS_CHANNELS):

        st.info(
            "ยังไม่ได้อัปโหลดไฟล์ Express (Online / Call Center) — "
            "อัปโหลดด้านบนแล้วกด 🚀 ประมวลผลข้อมูลอีกครั้ง"
        )

        return

    sales_by_channel = (
        channel_summary
        .assign(Channel=channel_summary["Channel"].astype(str))
        .set_index("Channel")["ยอดขาย"]
    )

    rows = []

    for channel in EXPRESS_CHANNELS:

        total_rows = express.get(channel)

        if total_rows is None:
            continue

        if total_rows.empty:

            st.warning(
                f"{channel}: ไม่พบแถว \"รวม\" ในไฟล์ Express "
                "จึงนับยอดเงิน Express เป็น 0"
            )

        express_sales = float(total_rows["ยอดที่ใช้"].sum())

        sales = float(sales_by_channel.get(channel, 0))

        rows.append(
            {
                "Channel": channel,
                "ยอดขาย (หลังรวม)": sales,
                "ยอดเงิน Express": express_sales,
                "ส่วนต่าง (ยอดขาย − Express)": sales - express_sales,
            }
        )

    table = pd.DataFrame(rows)

    total = {"Channel": "รวม"}

    for col in table.columns[1:]:
        total[col] = table[col].sum()

    table = pd.concat(
        [table, pd.DataFrame([total])],
        ignore_index=True
    )

    st.dataframe(
        table.style.format(
            {
                "ยอดขาย (หลังรวม)": "{:,.2f}",
                "ยอดเงิน Express": "{:,.2f}",
                "ส่วนต่าง (ยอดขาย − Express)": "{:,.2f}",
            }
        ),
        use_container_width=True,
        hide_index=True
    )

    st.caption(
        "ยอดขาย (หลังรวม) = ยอดขายในตาราง “สรุป Channel” ด้านบน | "
        "ยอด Express = ผลรวมของแถวที่มีคำว่า “รวม” "
        "(ใช้ตัวเลขตัวที่ 4 ของแถว เหมือนหน้า CN) | "
        "ส่วนต่าง = ยอดขาย − Express"
    )

    for channel in EXPRESS_CHANNELS:

        total_rows = express.get(channel)

        if total_rows is None:
            continue

        with st.expander(f"แถว “รวม” ที่ดึงจากไฟล์ Express — {channel}"):

            st.dataframe(
                total_rows,
                use_container_width=True,
                hide_index=True
            )


def _tab_raw(c):

    st.subheader("📄 ข้อมูลต้นฉบับ")

    raw_source = st.selectbox(
        "เลือกแหล่งข้อมูล",
        ["Shipnity", "ใบรายงาน"]
    )

    if raw_source == "Shipnity":
        raw = c.data["ship_raw"]
    else:
        raw = c.data["report_raw"]

    st.caption(
        f"{len(raw):,} แถว × "
        f"{len(raw.columns):,} คอลัมน์"
    )

    st.dataframe(
        raw,
        use_container_width=True,
        height=600
    )


# =========================================================
# Upload card
# =========================================================

def _upload_card():

    with card("upload"):

        section_title("อัปโหลดไฟล์")

        c1, c2 = st.columns(2)

        with c1:
            ship_file = st.file_uploader(
                "Shipnity",
                type=["xlsx", "xls"],
                key="ship"
            )

        with c2:
            report_file = st.file_uploader(
                "ใบรายงาน (ไฟล์รายงานเบล)",
                type=["xlsx", "xls"],
                key="report"
            )

        c3, c4, c5 = st.columns([4, 4, 2], vertical_alignment="bottom")

        with c3:
            online_file = st.file_uploader(
                "Express - Online (ไม่บังคับ)",
                type=["csv", "txt"],
                key="order_express_online"
            )

        with c4:
            call_file = st.file_uploader(
                "Express - Call Center (ไม่บังคับ)",
                type=["csv", "txt"],
                key="order_express_call"
            )

        with c5:
            run = st.button(
                "🚀 ประมวลผลข้อมูล",
                type="primary",
                use_container_width=True,
                key="order_run"
            )

        file_chips(
            [
                ("Shipnity", bool(ship_file)),
                ("ใบรายงาน", bool(report_file)),
                ("Express Online", bool(online_file)),
                ("Express Call Center", bool(call_file)),
            ]
        )

    return ship_file, report_file, online_file, call_file, run


# =========================================================
# Process
# =========================================================

def _process(ship_file, report_file, online_file=None, call_file=None):

    if not ship_file or not report_file:

        st.error("กรุณาอัปโหลดอย่างน้อย Shipnity และใบรายงาน")

        return

    try:

        with st.spinner("กำลังประมวลผลข้อมูล..."):

            ship_raw = read_excel(ship_file)

            report_raw = read_excel(report_file, sheet_name=-1)

            ship, ship_order, ship_channel = prepare_shipnity(ship_raw)

            report, report_order, report_channel = prepare_report(
                report_raw
            )

            result = build_comparison(
                ship,
                ship_order,
                report,
                report_order
            )

            express = build_express_totals(online_file, call_file)

            st.session_state.result = {
                "express": express,
                "ship_raw": ship_raw,
                "report_raw": report_raw,
                "ship": ship,
                "report": report,
                "ship_order": ship_order,
                "report_order": report_order,
                "result": result,
            }

            st.session_state.last_run = datetime.now()

        st.success("ประมวลผลสำเร็จ")

    except Exception as e:

        st.error(f"ประมวลผลไม่สำเร็จ: {e}")


# =========================================================
# Initial Page
# =========================================================

def _initial_page():

    md(
        '<div class="card">'
        '<h3>เริ่มต้นใช้งาน</h3>'
        '<p>อัปโหลดไฟล์ <b>Shipnity</b> และ <b>ใบรายงาน</b> '
        'ด้านบน แล้วกด <b>🚀 ประมวลผลข้อมูล</b></p>'
        '<p class="small">ระบบจะตรวจสอบออเดอร์ ยอดขาย และ Channel '
        'ระหว่างสองแหล่งข้อมูล • รองรับ Excel .xlsx / .xls</p>'
        '</div>'
    )


# =========================================================
# ผลการตรวจสอบ (ซ้าย)
# =========================================================

VIEWS = [
    "ทั้งหมด",
    "มีเฉพาะ Shipnity",
    "มีเฉพาะใบรายงาน",
    "มีทั้ง 2 แหล่ง",
    "ยอดขายไม่ตรงกัน",
    "ยอดขายตรงกัน",
]


def _pick_view(c, view):

    return {
        "ทั้งหมด": c.compare,
        "มีเฉพาะ Shipnity": c.only_ship,
        "มีเฉพาะใบรายงาน": c.only_report,
        "มีทั้ง 2 แหล่ง": c.both,
        "ยอดขายไม่ตรงกัน": c.different,
        "ยอดขายตรงกัน": c.same,
    }[view].copy()


def _display_table(table):
    """รวมเลขที่ออเดอร์เป็นคอลัมน์เดียว
    (ออเดอร์ที่มีเฉพาะใบรายงานใช้เลขจาก order_number แทน)"""

    out = table.copy()

    if "order_number" in out.columns:

        out["เลขที่ออเดอร์"] = (
            out["เลขที่ออเดอร์"].fillna(out["order_number"])
        )

        out = out.drop(columns=["order_number"])

    return out


def _status_chip(row):

    if row["_merge"] == STATUS_BOTH:

        if abs(row["ส่วนต่างยอดขาย"]) <= 0.01:
            return chip("ตรงกัน", "green")

        return chip("ยอดไม่ตรง", "amber")

    if row["_merge"] == STATUS_ONLY_SHIP:
        return chip("มีเฉพาะ Shipnity", "red")

    return chip("มีเฉพาะใบรายงาน", "red")


def _diff_cell(row, n):

    diff = row["ส่วนต่างยอดขาย"]

    if pd.isna(diff):
        return "-"

    cls = "neg" if abs(diff) > 0.01 else ""

    return f'<span class="{cls}">{diff:,.2f}</span>'


TABLE_COLS = [
    ("ลำดับ", lambda r, n: str(n), "c"),
    ("เลขที่ออเดอร์", lambda r, n: f'<b>{esc(r["เลขที่ออเดอร์"])}</b>', "l"),
    ("กลุ่ม", lambda r, n: esc(r["กลุ่ม"]), "l"),
    ("ยอดขาย Shipnity", lambda r, n: fmt_money(r["ยอดขาย_Shipnity"]), "r"),
    ("ยอดขายใบรายงาน", lambda r, n: fmt_money(r["ยอดขาย_ใบรายงาน"]), "r"),
    ("ส่วนต่าง", _diff_cell, "r"),
    ("สถานะ", lambda r, n: _status_chip(r), "l"),
]


def _results_panel(c):

    with card("results"):

        section_title(
            "ผลการตรวจสอบ",
            "เลือกมุมมองหรือค้นหาเลขที่ออเดอร์ได้ทันที"
        )

        kpi_cards(
            [
                {
                    "label": "ตรงกัน",
                    "count": len(c.same),
                    "total": c.total_orders,
                    "tone": "green",
                },
                {
                    "label": "ยอดขายไม่ตรงกัน",
                    "count": len(c.different),
                    "total": c.total_orders,
                    "tone": "amber",
                },
                {
                    "label": "มีเฉพาะฝั่งเดียว",
                    "count": len(c.only_ship) + len(c.only_report),
                    "total": c.total_orders,
                    "tone": "red",
                },
            ]
        )

        f1, f2, f3 = st.columns([3, 4, 3], vertical_alignment="bottom")

        with f1:
            view = st.selectbox("มุมมอง", VIEWS, key="order_view")

        with f2:
            search = st.text_input(
                "🔍 ค้นหาเลขที่ออเดอร์",
                placeholder="เช่น MM261007-301",
                key="order_search"
            )

        table = _display_table(_pick_view(c, view))

        if search.strip():

            table = table[
                table["เลขที่ออเดอร์"]
                .astype(str)
                .str.contains(
                    search.strip(),
                    case=False,
                    na=False,
                    regex=False
                )
            ]

        with f3:
            st.download_button(
                "⬇️ ดาวน์โหลด CSV",
                data=table.to_csv(index=False).encode("utf-8-sig"),
                file_name="order_reconciliation_result.csv",
                mime="text/csv",
                use_container_width=True
            )

        st.caption(f"พบ {len(table):,} รายการ")

        page_df, start = page_slice(table, "order_tbl")

        html_table(page_df, TABLE_COLS, start)

        page_controls("order_tbl", len(table), start)


# =========================================================
# สรุปภาพรวม (ขวา)
# =========================================================

def _summary_panel(c):

    with card("summary"):

        section_title("สรุปภาพรวม")

        stat_rows(
            [
                ("🛒", "จำนวนออเดอร์ทั้งหมด", f"{c.total_orders:,}"),
                ("💰", "ยอดขาย Shipnity", money(c.ship_sales)),
                ("🧾", "ยอดขายใบรายงาน", money(c.report_sales)),
                (
                    "⚖️",
                    "ส่วนต่างรวม (ใบรายงาน − Shipnity)",
                    money(c.sales_diff)
                ),
            ]
        )

        st.markdown("**สัดส่วนสถานะออเดอร์**")

        share = pd.DataFrame(
            {
                "สถานะ": ["ตรงกัน", "ยอดขายไม่ตรงกัน", "มีเฉพาะฝั่งเดียว"],
                "จำนวน": [
                    len(c.same),
                    len(c.different),
                    len(c.only_ship) + len(c.only_report),
                ],
            }
        )

        fig = px.pie(
            share,
            names="สถานะ",
            values="จำนวน",
            hole=.62,
            color="สถานะ",
            color_discrete_map={
                "ตรงกัน": "#16a34a",
                "ยอดขายไม่ตรงกัน": "#f59e0b",
                "มีเฉพาะฝั่งเดียว": "#dc2626",
            }
        )

        fig.update_layout(
            height=260,
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", y=-0.08, title=""),
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
            key="order_share_donut"
        )


# =========================================================
# Entry point
# =========================================================

def render_order_page():

    if "result" not in st.session_state:
        st.session_state.result = None

    ship_file, report_file, online_file, call_file, run = _upload_card()

    if run:
        _process(ship_file, report_file, online_file, call_file)

    if st.session_state.result is None:
        _initial_page()
        return

    c = _load_context()

    left, right = st.columns([7, 3])

    with left:
        _results_panel(c)

    with right:
        _summary_panel(c)

    section_title("รายละเอียดเพิ่มเติม")

    tab1, tab2, tab3 = st.tabs(
        [
            "📊 ภาพรวม",
            "📣 Channel",
            "📄 ข้อมูลต้นฉบับ"
        ]
    )

    with tab1:
        _tab_overview(c)

    with tab2:
        _tab_channel(c)

    with tab3:
        _tab_raw(c)
