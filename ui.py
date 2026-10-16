"""ส่วนประกอบ UI ที่ใช้ร่วมกันทั้งสองหน้า

การ์ด, หัวหน้า, KPI 3 ใบ, ป้ายสถานะ, ตาราง HTML, แบ่งหน้า
สีและหน้าตาอยู่ใน styles.py
"""

import html

import pandas as pd
import streamlit as st

TONE_ICON = {"green": "✓", "amber": "!", "red": "✕"}

PAGE_SIZES = (10, 25, 50, 100)


# =========================================================
# พื้นฐาน
# =========================================================

def esc(x):
    """escape ข้อความก่อนใส่ใน HTML (ค่าว่าง/NaN → '-')"""

    if x is None:
        return "-"

    if pd.api.types.is_scalar(x) and pd.isna(x):
        return "-"

    return html.escape(str(x))


def fmt_money(x):

    if x is None or pd.isna(x):
        return "-"

    return f"{float(x):,.2f}"


def md(s):
    """st.markdown(HTML) โดยตัดช่องว่างหน้าบรรทัด (กัน markdown มองเป็น code block)"""

    st.markdown(
        "".join(line.strip() for line in s.splitlines()),
        unsafe_allow_html=True
    )


def card(key):
    """การ์ดสีขาว (สไตล์อยู่ใน styles.py ผ่านคลาส st-key-card_*)"""

    try:
        return st.container(key=f"card_{key}")
    except TypeError:  # Streamlit เก่าที่ยังไม่มีพารามิเตอร์ key
        return st.container()


# =========================================================
# Sidebar
# =========================================================

def sidebar_brand():

    md(
        '<div class="brand">'
        '<div class="brand-logo">↩</div>'
        '<div>'
        '<div class="brand-title">Order Reconciliation</div>'
        '<div class="brand-sub">Shipnity • Express • CN</div>'
        '</div>'
        '</div>'
    )


def sidebar_status(last_run=None):

    if last_run:
        title = "ประมวลผลแล้ว"
        sub = f"ล่าสุด {last_run:%d/%m/%Y %H:%M}"
        dot = "dot on"
    else:
        title = "ยังไม่ได้ประมวลผล"
        sub = "อัปโหลดไฟล์แล้วกดประมวลผล"
        dot = "dot"

    md(
        '<div class="side-status">'
        f'<b><span class="{dot}"></span>{esc(title)}</b>'
        f'{esc(sub)}'
        '</div>'
    )


# =========================================================
# หัวหน้า / หัวข้อ
# =========================================================

def page_header(icon, title, subtitle):

    md(
        '<div class="page-head">'
        f'<div class="ic">{icon}</div>'
        '<div>'
        f'<div class="ph-title">{esc(title)}</div>'
        f'<div class="ph-sub">{esc(subtitle)}</div>'
        '</div>'
        '</div>'
    )


def section_title(title, sub=None):

    out = f'<div class="sec-title">{esc(title)}</div>'

    if sub:
        out += f'<div class="sec-sub">{esc(sub)}</div>'

    md(out)


# =========================================================
# ป้าย / KPI / สถิติ
# =========================================================

def chip(text, tone="gray"):
    """คืน HTML ของป้ายสถานะ (tone: green / amber / red / gray)"""

    return f'<span class="chip chip-{tone}"><i></i>{esc(text)}</span>'


def file_chips(items):
    """items = [(ชื่อไฟล์, อัปโหลดแล้วหรือยัง)]"""

    cells = [
        chip(
            f"{label} พร้อม" if ok else f"{label} รอไฟล์",
            "green" if ok else "gray"
        )
        for label, ok in items
    ]

    md(f'<div class="chips">{"".join(cells)}</div>')


def kpi_cards(items):
    """items = [{label, count, total, tone}]  (tone: green / amber / red)"""

    cells = []

    for it in items:

        total = it.get("total") or 0

        pct = (
            f' <span class="kpi-pct">({it["count"] / total * 100:.1f}%)</span>'
            if total
            else ""
        )

        cells.append(
            f'<div class="kpi kpi-{it["tone"]}">'
            f'<div class="kpi-ic">{TONE_ICON[it["tone"]]}</div>'
            '<div>'
            f'<div class="kpi-label">{esc(it["label"])}</div>'
            f'<div class="kpi-value">{int(it["count"]):,}{pct}</div>'
            '</div>'
            '</div>'
        )

    md(f'<div class="kpi-row">{"".join(cells)}</div>')


def stat_rows(rows):
    """rows = [(ไอคอน, ป้ายกำกับ, ค่า)]"""

    out = "".join(
        '<div class="stat">'
        f'<div class="stat-ic">{icon}</div>'
        '<div>'
        f'<div class="stat-label">{esc(label)}</div>'
        f'<div class="stat-value">{esc(value)}</div>'
        '</div>'
        '</div>'
        for icon, label, value in rows
    )

    md(out)


# =========================================================
# ตาราง HTML
# =========================================================

def html_table(df, cols, start=0):
    """
    cols = [(หัวคอลัมน์, fn(row, เลขลำดับ) -> HTML, จัดชิด)]
    จัดชิด: "l" ซ้าย, "r" ขวา, "c" กลาง
    ฟังก์ชันใน cols ต้อง escape ข้อมูลเองด้วย esc()
    """

    head = "".join(
        f'<th class="{a}">{esc(h)}</th>'
        for h, _, a in cols
    )

    body = []

    for n, (_, row) in enumerate(df.iterrows(), start=start + 1):

        tds = "".join(
            f'<td class="{a}">{fn(row, n)}</td>'
            for _, fn, a in cols
        )

        body.append(f"<tr>{tds}</tr>")

    if not body:

        body = [
            f'<tr><td colspan="{len(cols)}" class="empty">ไม่พบข้อมูล</td></tr>'
        ]

    md(
        '<div class="tbl-wrap"><table class="tbl">'
        f'<thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody>'
        '</table></div>'
    )


# =========================================================
# แบ่งหน้า
#
# page_slice()    ใช้ก่อนวาดตาราง  → ได้ชุดแถวของหน้านั้น
# page_controls() ใช้หลังวาดตาราง → ปุ่มเลือกจำนวน/หน้า
# ค่าเก็บใน session_state ด้วย key + "_size" / "_page"
# =========================================================

def _page_state(key, total):

    size = st.session_state.get(f"{key}_size", PAGE_SIZES[0])

    pages = max(1, -(-total // size))

    page = min(max(int(st.session_state.get(f"{key}_page", 1)), 1), pages)

    return size, pages, page


def page_slice(df, key):

    size, pages, page = _page_state(key, len(df))

    st.session_state[f"{key}_page"] = page

    start = (page - 1) * size

    return df.iloc[start:start + size], start


def page_controls(key, total, start):

    size, pages, page = _page_state(key, total)

    end = min(start + size, total)

    c1, c2, c3 = st.columns([3, 4, 3], vertical_alignment="center")

    with c1:

        st.selectbox(
            "แสดงต่อหน้า",
            PAGE_SIZES,
            key=f"{key}_size"
        )

    with c2:

        shown_from = start + 1 if total else 0

        st.caption(
            f"แสดง {shown_from:,}–{end:,} จาก {total:,} รายการ"
        )

    with c3:

        st.number_input(
            f"หน้า (จาก {pages:,})",
            min_value=1,
            max_value=pages,
            step=1,
            key=f"{key}_page"
        )
