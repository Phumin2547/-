"""หน้า "รายละเอียดออเดอร์" — เทียบใบกำกับ Express (Online / Call Center) กับ Shipnity โปรโมชั่น

แบ่งเป็น 4 แท็บ ข้อมูลแต่ละอย่างแสดงที่เดียว:
    📊 ภาพรวม          เทียบยอด CSV vs Shipnity + สรุปตามขนส่ง
    ✅ ตรวจใบกำกับ      สถานะรายใบกำกับ IK / WG / IE
    🧩 รายการสินค้า      ออเดอร์และรหัสสินค้าในแต่ละใบกำกับ
    🔎 ค้นหาออเดอร์      ค้นหาเลขออเดอร์ ดูรายบรรทัด

ไฟล์ที่ใช้: 1) Shipnity โปรโมชั่น (.xlsx)  2) Express Online (.csv)  3) Express Call Center (.csv)
"""

import io
import os
import re

import pandas as pd
import plotly.express as px
import streamlit as st

from frontend.ui import (
    card,
    chip,
    esc,
    file_chips,
    fmt_money,
    html_table,
    kpi_cards,
    md,
    page_controls,
    page_header,
    page_slice,
    section_title,
    stat_rows,
)
from backend.utils import money

from frontend.shipnity_widgets import pick_period as _pick_period, secrets as _secrets, today_th as _today_th
from backend.order_detail_logic import (  # noqa: E402
    INV_CHANNEL_COL,
    INV_CUSTOMER_COL,
    INV_GROUP_COL,
    INV_SALES_COL,
    INV_ORDER_COL,
    INV_NO_COL,
    INV_CODE_COL,
    INV_NAME_COL,
    INV_QTY_COL,
    INV_NET_COL,
    INV_SHIPPING_CODE,
    INV_NO_RE,
    _csv_lines,
    _inv_norm_code,
    _parse_invoice_report,
    _parse_csv_items,
    _carrier_of,
    _invoice_compare,
    _build_order_detail,
    _excel_bytes,
)

try:
    from backend import shipnity_api as sn
    from backend import shipnity_promo as sp
    from backend import shipnity_audit as au
    SN_ERROR = ""
except ImportError as e:      # ไม่มี shipnity_api.py / shipnity_promo.py / requests
    sn = sp = au = None
    SN_ERROR = str(e)

_invoice_compare = st.cache_data(show_spinner=False)(_invoice_compare)
_excel_bytes = st.cache_data(show_spinner=False)(_excel_bytes)

FILES_KEY = "od_files"          # {ช่องอัปโหลด: {"name", "data"}}
COUNTER_KEY = "od_up_counts"    # ตัวนับ key ของช่องอัปโหลด (ไว้ล้างช่องหลังเลือกไฟล์)
RAN_KEY = "od_ran"


# =========================================================
# ส่วนประมวลผล + แสดงผล (พอร์ตจากโน้ตบุ๊ก)
# =========================================================















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
            show_bad = (
                st.toggle("เฉพาะออเดอร์ในใบกำกับที่ไม่ตรง", key="od_order_suspect")
                if res is not None else False
            )

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
# ดึงจาก Shipnity + (ตัวเลือก) เทียบกับ Express
# =========================================================

API_KEY = "od_api"          # ผลดึงล่าสุด {"lines","info","label","time"}
CMP_KEY = "od_compare"


@st.cache_data(show_spinner=False)
def _promo_bytes(lines, known):
    """lines (+รหัสสินค้าที่ตัดตัวนำหน้าแล้ว) → ไฟล์ Excel แบบบล็อกที่ตรรกะเทียบเดิมอ่านได้"""

    return sp.to_block_xlsx(sp.apply_codes(lines, set(known) if known else None))


def _step(n, title, hint=""):
    """หัวข้อขั้นตอนของหน้า"""

    md(
        f'<div class="step-head"><span class="n">{n}</span><span class="t">{esc(title)}</span>'
        + (f'<span class="h">· {esc(hint)}</span>' if hint else "")
        + "</div>"
    )


STAGE_KEY = "od_stage"                # home | setup | result | file
API_FILES_KEY = "od_api_files"        # ไฟล์ Express ของโหมดดึงจาก Shipnity (แยกจากโหมดอัปโหลดแบบเดิม)


def _go(stage):
    st.session_state[STAGE_KEY] = stage
    st.rerun()


def _fetch_now(cfg, d1, d2, max_pages):
    """ดึงจาก Shipnity แล้วเก็บผลใน session_state → True ถ้าสำเร็จ"""

    bar = st.progress(0.0, text="กำลังเชื่อมต่อ Shipnity...")

    def on_page(n, second):

        if isinstance(second, int):       # (หน้าที่ดึงแล้ว, หน้าทั้งหมด) จากการกรองฝั่ง Shipnity
            bar.progress(min(n / max(second, 1), 1.0), text=f"ดึงแล้ว {n:,} / {second:,} หน้า")
        else:                             # (หน้าที่ดึงแล้ว, เวลาเก่าสุด) จากการไล่ดึงเอง
            bar.progress(
                min(n / max_pages, 1.0),
                text=f"ดึงแล้ว {n:,} หน้า · เก่าสุด {second:%d/%m/%Y %H:%M}"
            )

    try:
        lines, info = sp.fetch_lines(cfg, d1, d2, max_pages=max_pages, progress=on_page)

    except sn.ShipnityError as e:
        bar.empty()
        st.error(str(e))
        return False

    except Exception as e:  # noqa: BLE001
        bar.empty()
        st.error(f"ดึงข้อมูลไม่สำเร็จ: {type(e).__name__}: {e}")
        return False

    bar.empty()

    if lines.empty:
        st.session_state.pop(API_KEY, None)
        st.warning("ไม่พบรายการที่พิมพ์ในช่วงวันที่ที่เลือก")
        return False

    st.session_state[API_KEY] = {
        "lines": lines,
        "info": info,
        "label": f"{d1:%d/%m/%Y}" + (f" – {d2:%d/%m/%Y}" if d2 != d1 else ""),
        "time": pd.Timestamp.now().strftime("%d/%m/%Y %H:%M:%S"),
    }

    return True


def _home_view():
    """หน้า 1: เลือกแหล่งข้อมูล"""

    section_title("เริ่มต้นโหลดข้อมูล", "เลือกแหล่งข้อมูลที่ต้องการนำมาวิเคราะห์")

    c1, c2 = st.columns(2)

    with c1:
        with card("od_home_file"):
            md('<div class="src-card"><div class="src-ic">📄</div><div class="src-t">โหลดจากไฟล์</div>'
               '<div class="src-d">อัปโหลดไฟล์ Excel หรือ CSV<br>เพื่อวิเคราะห์ข้อมูลของคุณ</div></div>')

            if st.button("เลือกไฟล์", use_container_width=True, key="od_home_file_btn"):
                _go("file")

    with c2:
        with card("od_home_api"):
            md('<div class="src-card"><div class="src-ic">☁️</div><div class="src-t">ดึงจาก Shipnity</div>'
               '<div class="src-d">เชื่อมต่อระบบ Shipnity<br>เพื่อดึงข้อมูลออเดอร์ตามช่วงวันที่</div></div>')

            if st.button("เชื่อมต่อ Shipnity", type="primary", use_container_width=True, key="od_home_api_btn"):
                _go("setup")

    st.info("คุณสามารถเลือกเปรียบเทียบข้อมูลกับไฟล์ Express ได้ในขั้นตอนถัดไป (ไม่จำเป็นต้องเลือก)")

    if st.session_state.get(API_KEY):
        if st.button("ดูผลลัพธ์ล่าสุด →", key="od_home_last"):
            _go("result")


def _setup_view():
    """หน้า 2: เลือกช่วงวันที่ + (ตัวเลือก) เทียบกับไฟล์ Express แล้วกดดึงและวิเคราะห์"""

    if st.button("← กลับหน้าหลัก", key="od_setup_back"):
        _go("home")

    if sn is None or sp is None:
        st.error(
            f"โหลดโมดูล Shipnity ไม่ได้ ({SN_ERROR}) — คัดลอก `shipnity_api.py`, `shipnity_promo.py`, "
            "`shipnity_request_promo.json` ไว้โฟลเดอร์เดียวกับ `app.py` (และ `pip install requests`)"
        )
        return

    files = st.session_state.setdefault(API_FILES_KEY, {})

    today = _today_th()
    cfg = sn.build_config(_secrets())
    problems = sn.config_problems(cfg)

    if not os.path.exists(sp.PROMO_TEMPLATE):
        problems.append("ไม่พบไฟล์ shipnity_request_promo.json ข้างไฟล์แอป")

    with card("od_setup"):

        md('<div class="setup-head"><span class="ic">☁️</span><div>'
           '<div class="t">ดึงข้อมูลจาก Shipnity</div>'
           '<div class="d">เลือกช่วงวันที่พิมพ์ที่ต้องการดึงข้อมูลออเดอร์</div></div></div>')

        period = _pick_period(today, "od")

        compare = st.checkbox(
            "เปรียบเทียบข้อมูลกับไฟล์ Express",
            value=bool(files),
            key="od_cmp",
            help="ไม่จำเป็นต้องเลือก — ถ้าไม่เลือก จะแสดงผลจาก Shipnity อย่างเดียว"
        )

        staged = {}

        if compare:

            st.caption("อัปโหลดไฟล์ CSV จาก Express (เลือกได้ทั้ง 2 ไฟล์ หรือไฟล์เดียว) ใช้เติมเลขใบกำกับ IK/WG/IE, ใบสั่งขาย SK และเทียบยอด")

            u1, u2 = st.columns(2)

            for col, sid, label in ((u1, "online", "Express Online (.csv)"), (u2, "call", "Express Call Center (.csv)")):

                with col:

                    up = st.file_uploader(label, type=["csv", "txt"], key=f"od_up_{sid}")

                    if up:
                        staged[sid] = {"name": up.name, "data": up.getvalue()}
                    elif sid in files:
                        st.caption(f"ใช้ไฟล์เดิม: {files[sid]['name']}")

        run = st.button("ดึงข้อมูลและวิเคราะห์ →", type="primary", use_container_width=True, key="od_run")

    if period is None:
        return

    d1, d2 = period
    days = (d2 - d1).days + 1

    if days > 15:
        st.warning(
            f"ช่วง {days:,} วัน — รายงานนี้ดึงรายบรรทัดสินค้า จำนวนหน้ามากกว่าหน้าออเดอร์ 2–3 เท่า อาจใช้เวลานาน"
        )

    if not run:

        for pr in problems:
            st.info(pr)

        return

    if problems:

        for pr in problems:
            st.error(pr)

        return

    if compare and not staged and not files:
        st.warning("เลือกเปรียบเทียบกับไฟล์ Express แล้ว แต่ยังไม่ได้อัปโหลดไฟล์ — อัปโหลดอย่างน้อย 1 ไฟล์ หรือยกเลิกติ๊ก")
        return

    max_pages = min(8000, max(120, ((today - d1).days + 1) * 150))

    if not _fetch_now(cfg, d1, d2, max_pages):
        return

    if compare:
        files.update(staged)
    else:
        files.clear()

    _go("result")


def _express_values(files):
    online = files.get("online", {}).get("data", b"")
    call = files.get("call", {}).get("data", b"")
    return bool(online or call), online, call


def _shipnity_overview(res):
    """ภาพรวมจาก Shipnity อย่างเดียว (ยังไม่เทียบ Express)"""

    comp = res["comparison"]
    tot = comp[comp["ประเภทช่องทาง"] == "รวมทั้งหมด"].iloc[0]

    with card("od_ship_sum"):

        section_title("ภาพรวมจาก Shipnity", "1 บล็อก = 1 ใบกำกับ (ออเดอร์ที่ไม่มีเลขใบกำกับรวมเป็นบล็อกตามขนส่ง)")

        stat_rows([
            ("🧾", "จำนวนบิล (บล็อก)", f"{tot['จำนวนบิล Shipnity']:,.0f}"),
            ("📦", "จำนวนออเดอร์", f"{tot['จำนวนออเดอร์ Shipnity']:,.0f}"),
            ("💰", "ยอดขายรวม", money(tot["ยอดขาย Shipnity"])),
        ])


    _carrier_summary(res["carrier_blocks"])


def _cancelled_table(all_lines, restored=None, checked=False):
    """ตารางออเดอร์ยกเลิก พร้อมผลตรวจว่า "ตัดถูก" หรือ "คืนเข้าบิล" (หลังอัป CSV Express)"""

    canc = all_lines[all_lines["ยกเลิก"]]

    back = {}

    if restored is not None and len(restored):
        back = dict(zip(restored["เลขที่ออเดอร์"], restored["เลขที่ใบกำกับ"]))

    t = canc.groupby("เลขที่ออเดอร์", as_index=False, sort=False).agg(
        ช่องทาง=("ช่องทางการเปิดบิล", "first"), ขนส่ง=("ขนส่ง", "first"),
        ยอดขาย=("ยอดขาย", "first"), วันที่พิมพ์=("วันที่พิมพ์", "first"),
        หมายเหตุ=("หมายเหตุ", "first"), บรรทัด=("ยอดขาย", "size")
    )

    def verdict(o):

        if o in back:
            return (
                "✅ คืนเข้าบิล " + str(back[o]) + " — Shipnity ว่ายกเลิก แต่ Express ลงบิลไว้แล้ว "
                "(ยอดตรงกับส่วนต่างของใบกำกับ) น่าจะยกเลิกหลังลงบิลไปแล้ว การตัดทิ้งจะผิด"
            )

        if checked:
            return "🚫 ตัดถูก — ไม่มีบิลใน Express ที่ยอดขาดตรงกับออเดอร์นี้ (ไม่ถูกลงบิล)"

        return "🚫 ตัดทิ้งตามสถานะ Shipnity — ยังไม่ได้อัป CSV Express ตรวจ"

    t.insert(1, "ผลตรวจ", t["เลขที่ออเดอร์"].map(verdict))

    st.dataframe(t, use_container_width=True, hide_index=True)


def _fetch_summary(lines, info):
    """สรุปทันทีหลังดึงจาก Shipnity: มีข้อมูลเท่าไร แบ่งเป็นกลุ่ม (บล็อก) อะไรบ้าง"""

    orders = lines.drop_duplicates("เลขที่ออเดอร์")
    all_lines = info.get("all_lines")

    cut = 0
    if all_lines is not None and "ยกเลิก" in all_lines.columns:
        cut = all_lines[all_lines["ยกเลิก"]]["เลขที่ออเดอร์"].nunique()

    blocks = sp.blocks_of(lines)

    with card("od_fetch_sum"):

        section_title("ผลที่ดึงได้จาก Shipnity", "ตรวจว่าจำนวนและกลุ่มตรงกับที่คาดไหน")

        stat_rows([
            ("🧾", "จำนวนบรรทัดสินค้า", f"{len(lines):,}"),
            ("📦", "จำนวนออเดอร์", f"{len(orders):,}"),
            ("💰", "ยอดขายรวม", money(orders["ยอดขาย"].sum())),
            ("🗂️", "จำนวนกลุ่ม (บล็อก)", f"{len(blocks):,}"),
            ("🚫", "ออเดอร์ยกเลิกที่ตัดทิ้ง", f"{cut:,}"),
        ])

        kept = info.get("kept_cancelled")

        if kept is not None and len(kept):
            with st.expander(f"⚠️ Shipnity ว่ายกเลิกแต่คงไว้ในยอด ({len(kept):,}) — ตรวจว่าทีมยังลงบิลจริงไหม"):
                st.caption("ไม่มีหมายเหตุยกเลิก จึงยังนับเป็นยอดขาย ถ้าไม่ใช่ ให้เติมคำในหมายเหตุหรือแก้ CUT_CANCELLED_NOTE_RE")
                st.dataframe(kept, use_container_width=True, hide_index=True)

        if cut:
            with st.expander(f"🚫 ดูออเดอร์ยกเลิกที่ตัดทิ้ง ({cut:,})"):
                st.caption("ออเดอร์ที่ Shipnity ติดสถานะ \"ยกเลิก\" แอปไม่นับในตัวเลขด้านบน")
                _cancelled_table(all_lines)

        st.markdown("**สะพานตัวเลข: ดึงมาได้เท่าไร → นับจริงเท่าไร**")

        br = au.bridge(all_lines, lines)

        st.dataframe(
            br,
            column_config={
                "ออเดอร์": st.column_config.NumberColumn("ออเดอร์", format="%d"),
                "บรรทัด": st.column_config.NumberColumn("บรรทัด", format="%d"),
                "ยอดขาย": st.column_config.NumberColumn("ยอดขาย", format="%.2f"),
            },
            use_container_width=True,
            hide_index=True
        )

        checks = au.quality_checks(lines)
        bad = [t for lv, t in checks if lv == "warn"]
        note = [t for lv, t in checks if lv == "info"]

        if bad:
            st.warning("ควรตรวจก่อนใช้งาน:\n" + "\n".join(f"- {t}" for t in bad))
        else:
            st.success("ตรวจคุณภาพข้อมูลผ่าน: " + " · ".join(t for lv, t in checks if lv == "ok"))

        if note:
            with st.expander("ข้อสังเกตเพิ่มเติม"):
                for t in note:
                    st.markdown(f"- {t}")

        recs = []

        for (chn, code), g in lines.groupby(["ช่องทางการเปิดบิล", "รหัสลูกค้า"]):
            o = g.drop_duplicates("เลขที่ออเดอร์")
            v = o["ขนส่ง"].value_counts()
            recs.append({
                "ช่องทางการเปิดบิล": chn,
                "รหัสลูกค้า": code,
                "ขนส่งที่รวมอยู่ (ออเดอร์)": ", ".join(f"{k} ({n:,})" for k, n in v.items()),
                "ออเดอร์": len(o),
                "บรรทัด": len(g),
                "ยอดขาย": float(o["ยอดขาย"].sum()),
            })

        grp = pd.DataFrame(recs).sort_values(["ช่องทางการเปิดบิล", "ยอดขาย"], ascending=[True, False]).reset_index(drop=True)
        grp["% ยอดขาย"] = grp["ยอดขาย"] / max(grp["ยอดขาย"].sum(), 1) * 100

        st.markdown("**ทุกกลุ่ม (1 กลุ่ม = 1 บล็อก = 1 ใบกำกับที่คาดว่าจะเปิด)**")
        st.dataframe(
            grp,
            column_config={
                "ออเดอร์": st.column_config.NumberColumn("ออเดอร์", format="%d"),
                "บรรทัด": st.column_config.NumberColumn("บรรทัด", format="%d"),
                "ยอดขาย": st.column_config.NumberColumn("ยอดขาย", format="%.2f"),
                "% ยอดขาย": st.column_config.ProgressColumn("% ยอดขาย", format="%.1f%%", min_value=0, max_value=100),
            },
            use_container_width=True,
            hide_index=True
        )

        with st.expander("รายละเอียดเพิ่มเติม: ช่องทางเปิดบิล · วิธีชำระ · ออเดอร์ขอใบกำกับภาษี"):

            ch = (
                orders.groupby("ช่องทางการเปิดบิล")
                .agg(ออเดอร์=("เลขที่ออเดอร์", "nunique"), ยอดขาย=("ยอดขาย", "sum"))
                .reset_index()
            )
            ch["กลุ่ม (บล็อก)"] = ch["ช่องทางการเปิดบิล"].map(blocks.groupby("ช่องทางการเปิดบิล").size())
            ch["ยอดขาย"] = ch["ยอดขาย"].map(lambda v: f"{v:,.2f}")

            st.markdown("**แยกตามช่องทางเปิดบิล**")
            st.dataframe(ch, use_container_width=True, hide_index=True)

            pay = orders.groupby("ชำระ")["ยอดขาย"].agg(["size", "sum"]).reset_index()
            pay.columns = ["วิธีชำระ", "ออเดอร์", "ยอดขาย"]
            pay["ยอดขาย"] = pay["ยอดขาย"].map(lambda v: f"{v:,.2f}")

            c1, c2 = st.columns(2)

            with c1:
                st.markdown("**วิธีชำระ**")
                st.dataframe(pay, use_container_width=True, hide_index=True)

            with c2:
                tax = orders[orders["รหัสลูกค้า"].astype(str).str.startswith(sp.TAX_CODE_PREFIX)]
                st.markdown(f"**ออเดอร์ขอใบกำกับภาษี (แยกเป็นบิลของตัวเอง): {len(tax):,}**")
                if len(tax):
                    st.dataframe(
                        tax[["เลขที่ออเดอร์", "ช่องทางการเปิดบิล", "ขนส่ง", "ยอดขาย"]],
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.caption("ไม่มี")


        st.caption(
            f"ช่วงเวลาพิมพ์ {lines['วันที่พิมพ์'].min()} – {lines['วันที่พิมพ์'].max()} · "
            f"ดึง {info.get('pages', 0):,} หน้า · รหัสสินค้าไม่ซ้ำ {lines['รหัสสินค้า (ดิบ)'].nunique():,} รายการ"
        )


def _variance_card(rec, bridge_df, summary):
    """สะพานยอดขาย Shipnity → Express พร้อมสาเหตุและหลักฐานรายใบกำกับ"""

    with card("od_variance"):

        section_title("ส่วนต่างระหว่าง Shipnity กับ Express เกิดจากอะไร", "ทุกส่วนต่างต้องมีสาเหตุและหลักฐานรองรับ")

        total = summary["total_diff"]

        if abs(total) < 0.005:
            st.success("ยอดขายรวมของ Shipnity กับ Express ตรงกัน")
        else:
            n_unknown = int((rec["กลุ่มสาเหตุ"] == "ไม่ทราบสาเหตุ").sum())
            st.warning(
                f"ส่วนต่างรวม {total:+,.2f} บาท · จัดกลุ่มสาเหตุได้ {summary['explained_pct']:.0f}% "
                + (f"· มี {n_unknown} ใบที่ยังไม่ทราบสาเหตุ ({summary['unknown']:+,.2f} บาท)" if n_unknown else "")
            )

        st.dataframe(
            bridge_df,
            column_config={
                "ใบกำกับ": st.column_config.NumberColumn("ใบกำกับ", format="%d"),
                "ยอด": st.column_config.NumberColumn("ยอด (บาท)", format="%.2f"),
            },
            use_container_width=True,
            hide_index=True
        )

        view = rec.drop(columns=[c for c in ("_คืน",) if c in rec.columns])

        diff = view[view["ส่วนต่าง"].abs() >= 0.005]
        low = view[(view["ส่วนต่าง"].abs() < 0.005) & view["ความมั่นใจการจับคู่"].str.startswith("ต่ำ")]

        cfg = {
            "ยอด CSV": st.column_config.NumberColumn("ยอด CSV", format="%.2f"),
            "ยอด Shipnity": st.column_config.NumberColumn("ยอด Shipnity", format="%.2f"),
            "ส่วนต่าง": st.column_config.NumberColumn("ส่วนต่าง", format="%+.2f"),
        }

        if len(diff):
            st.markdown("**ใบกำกับที่ต่าง (เรียงตามขนาดของส่วนต่าง)**")
            st.dataframe(diff, column_config=cfg, use_container_width=True, hide_index=True)

        if len(low):
            st.markdown("**ใบที่ยอดตรงแต่จับคู่ด้วยยอดใกล้เคียง (ความมั่นใจต่ำ — ตรวจให้แน่ใจว่าไม่ได้จับสลับ)**")
            st.dataframe(low, column_config=cfg, use_container_width=True, hide_index=True)

        with st.expander("ดูทุกใบกำกับ"):
            st.dataframe(view, column_config=cfg, use_container_width=True, hide_index=True)

        st.caption(
            "สาเหตุที่แอปบอกได้: ยกเลิกหลังลงบิล (ยอดตรงส่วนต่างพอดี) · ส่วนลด/ราคา (สินค้าเท่ากันแต่ยอดต่าง) · "
            "สินค้าต่างกัน (เทียบรหัสสินค้า) · บิลฝั่งเดียว — แอปไม่รู้ว่าทำไมจึงให้ส่วนลด จึงบอกแค่ว่าเกิดขึ้น"
        )


def _mapping_check(lines, info):

    chk = sp.mapping_check(lines)

    with st.expander("🔍 เครื่องมือตรวจสอบ (เทียบกับไฟล์ export · ช่วงเวลาพิมพ์ · ตารางแมปขนส่ง)"):

        st.caption(
            f"{chk['lines']:,} บรรทัด · {chk['orders']:,} ออเดอร์ · {len(chk['blocks']):,} บล็อก · "
            f"ดึง {info['pages']:,} หน้า"
        )

        tp = sp.time_profile(lines)

        if not tp.empty:
            st.markdown("**ช่วงเวลาพิมพ์ที่ดึงได้** (ดูว่าครอบคลุมทั้งวันไหม เทียบกับไฟล์ที่ส่งออกจาก Shipnity)")
            st.caption(
                f"เวลาพิมพ์แรกสุด–ล่าสุด: {lines['วันที่พิมพ์'].min()} – {lines['วันที่พิมพ์'].max()}"
            )
            st.dataframe(tp, use_container_width=True, hide_index=True)

        all_lines = info.get("all_lines")

        if all_lines is not None and len(all_lines):

            buf = io.BytesIO()
            all_lines.to_excel(buf, index=False, engine="openpyxl")

            st.download_button(
                "⬇️ ดาวน์โหลดข้อมูลที่ดึงมาทั้งหมด (รวมออเดอร์ยกเลิก) ไว้เทียบกับไฟล์ Shipnity",
                data=buf.getvalue(),
                file_name="shipnity_fetched_lines.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="od_fetched_dl"
            )

        if all_lines is not None and len(all_lines) and "ยกเลิก" in all_lines.columns:
            canc = all_lines[all_lines["ยกเลิก"]]
            if len(canc):
                st.markdown("**ออเดอร์ยกเลิกที่แอปตัดทิ้ง** (ถ้าทีมยังลงบิลออเดอร์ไหนไว้ใน Express ให้ดูยอดตรงนี้)")
                st.dataframe(
                    canc.groupby("เลขที่ออเดอร์", as_index=False).agg(
                        ยอดขาย=("ยอดขาย", "first"), ขนส่ง=("ขนส่ง", "first"),
                        วันที่พิมพ์=("วันที่พิมพ์", "first"), บรรทัด=("ยอดขาย", "size")
                    ),
                    use_container_width=True, hide_index=True
                )

        if chk["unknown"]:
            st.warning(
                "พบขนส่งที่ยังไม่มีรหัสลูกค้า: " + ", ".join(chk["unknown"])
                + " — เพิ่มกฎที่ CUSTOMER_RULES ใน backend/shipnity_promo.py"
            )

        if info.get("first_page_times"):
            st.markdown("**เวลาพิมพ์ของบรรทัดในหน้าแรกที่ดึงได้** (ใช้ตรวจว่า Shipnity เรียงจากใหม่ไปเก่าไหม)")
            st.code(" → ".join(info["first_page_times"]))

        st.markdown("**บล็อก (1 บล็อก = 1 ช่องทาง + รหัสลูกค้า)**")
        st.dataframe(chk["blocks"], use_container_width=True, hide_index=True)

        st.markdown("**ขนส่ง → รหัสลูกค้า**")
        st.dataframe(chk["ships"], use_container_width=True, hide_index=True)

        st.markdown("**ช่องทางการเปิดบิลที่จับได้** (contactMethod ที่มีคำว่า phone = Callcenter/SE)")
        st.dataframe(chk["by_channel"], use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ ดาวน์โหลดข้อมูลรายบรรทัดที่ดึงมา (CSV)",
            data=lines.to_csv(index=False).encode("utf-8-sig"),
            file_name="shipnity_lines.csv",
            mime="text/csv",
            key="od_lines_dl"
        )

        st.markdown("**เทียบกับไฟล์ที่ export จาก Shipnity (ช่วงเดียวกัน)** — ไว้ตรวจว่าดึงมาตรงไหม")

        up = st.file_uploader("ไฟล์ export (.xlsx)", type=["xlsx"], key="od_export_cmp")

        if up:

            try:
                cmp = sp.compare_with_export(lines, pd.read_excel(io.BytesIO(up.getvalue())))
            except Exception as e:  # noqa: BLE001
                st.error(f"เทียบไม่ได้: {e}")
                return

            st.caption(
                f"API: {cmp['api_lines']:,} บรรทัด · {cmp['api_orders']:,} ออเดอร์ · ยอด {cmp['api_sales']:,.2f}   |   "
                f"ไฟล์: {cmp['file_lines']:,} บรรทัด · {cmp['file_orders']:,} ออเดอร์"
                + (f" · ยอด {cmp['file_sales']:,.2f}" if cmp["file_sales"] is not None else "")
                + f"   |   ตรงกัน {cmp['both']:,} ออเดอร์ · บรรทัดหน้าตาเหมือนกันใน API {cmp['dup_lines']:,} (อาจเป็นสินค้าซ้ำในออเดอร์เดียวกันจริง)"
            )

            st.markdown(f"**มีใน API แต่ไม่มีในไฟล์ ({len(cmp['only_api']):,} ออเดอร์)**")
            st.dataframe(cmp["only_api"], use_container_width=True, hide_index=True)

            st.markdown(f"**มีในไฟล์แต่ไม่มีใน API ({len(cmp['only_file']):,} ออเดอร์)**")
            st.dataframe(cmp["only_file"], use_container_width=True, hide_index=True)

            st.markdown("**จำนวนบรรทัดแยกตามชั่วโมงพิมพ์**")
            st.dataframe(cmp["hours"], use_container_width=True, hide_index=True)


# =========================================================
# หน้าหลัก
# =========================================================

def _compare_tabs(res, orders_df, lines_df, promo, online, call):
    """ปุ่มดาวน์โหลด + 4 แท็บผลเทียบ (ใช้ร่วมกันทั้งโหมดดึงจาก Shipnity และโหมดอัปโหลดไฟล์)"""

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


# =========================================================
# โหมดอัปโหลดไฟล์ (แบบเดิม): Shipnity โปรโมชั่น .xlsx + Express 2 ไฟล์
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


def _render_upload_mode():

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

    _compare_tabs(res, orders_df, lines_df, promo, online, call)


def _result_header(api, files, compare):
    """แถบสถานะด้านบนของหน้าผลลัพธ์ + ปุ่มดึงใหม่/กลับหน้าหลัก"""

    pills = [
        f'<span class="pill tone-{"purple" if compare else "green"}">'
        f'{"เปรียบเทียบไฟล์" if compare else "ข้อมูลจาก Shipnity"}</span>',
        f'<span class="pill">📅 Shipnity · พิมพ์ <b>{esc(api["label"])}</b></span>',
    ]

    for sid, name in (("online", "Online"), ("call", "Call Center")):
        if sid in files:
            pills.append(f'<span class="pill">📄 {name}: <b>{esc(files[sid]["name"])}</b></span>')

    h1, h2, h3, h4 = st.columns([8, 3, 1.6, 1.6], vertical_alignment="center")

    with h1:
        md('<div class="status-bar">' + "".join(pills) + "</div>")

    with h2:
        md(f'<div class="updated">อัปเดตล่าสุด {esc(api["time"])}</div>')

    with h3:
        if st.button("🔄 ดึงใหม่", key="od_res_refetch", use_container_width=True):
            _go("setup")

    with h4:
        if st.button("← หน้าหลัก", key="od_res_home", use_container_width=True):
            _go("home")


def _kpi_html(cards):
    """cards = [(ไอคอน, ป้าย, ค่า, ข้อความรอง, โทน)]"""

    cells = "".join(
        f'<div class="kpi2 tone-{tone}"><div class="ic">{ic}</div><div>'
        f'<div class="l">{esc(label)}</div><div class="v">{esc(value)}</div>'
        f'<div class="s">{esc(sub)}</div></div></div>'
        for ic, label, value, sub, tone in cards
    )

    md(f'<div class="kpi2-row">{cells}</div>')


def _result_kpis(lines, info, res, compare):

    orders = lines.drop_duplicates("เลขที่ออเดอร์")
    all_l = info.get("all_lines")
    kept = info.get("kept_cancelled")

    cut = 0
    if all_l is not None and "ยกเลิก" in all_l.columns:
        cut = all_l[all_l["ยกเลิก"]]["เลขที่ออเดอร์"].nunique()

    if compare and res is not None:

        inv = res["inv_check"]
        n = max(len(inv), 1)
        ok = int((inv["สถานะ"] == "ตรงกัน").sum())
        bad = int((inv["สถานะ"] == "ยอดไม่ตรง").sum())
        one = int(inv["สถานะ"].isin(["ไม่มีใน Shipnity", "ไม่มีใน CSV"]).sum())
        tot = res["comparison"][res["comparison"]["ประเภทช่องทาง"] == "รวมทั้งหมด"].iloc[0]

        _kpi_html([
            ("🧾", "ใบกำกับตรงกัน", f"{ok:,}", f"{ok / n * 100:.1f}% ของ {len(inv):,} ใบ", "green"),
            ("⚠️", "ยอดไม่ตรง", f"{bad:,}", f"{bad / n * 100:.1f}%", "amber"),
            ("✖️", "มีฝั่งเดียว", f"{one:,}", f"{one / n * 100:.1f}%", "red"),
            ("💰", "ผลต่างยอดขาย (Shipnity − CSV)", f"{tot['ผลต่างยอดขาย']:+,.2f}",
             f"ผลต่างจำนวนบิล {tot['ผลต่างจำนวนบิล']:+,.0f}", "purple"),
        ])

    else:

        carriers = orders["ขนส่ง"].nunique()
        blocks = len(sp.blocks_of(lines))
        odd = cut + (len(kept) if kept is not None else 0)

        _kpi_html([
            ("🛒", "จำนวนออเดอร์", f"{len(orders):,}", f"{len(lines):,} บรรทัดสินค้า", "blue"),
            ("💰", "ยอดขายรวม", money(orders["ยอดขาย"].sum()), "บาท", "green"),
            ("🚚", "ขนส่ง", f"{carriers:,} ราย", f"{blocks:,} กลุ่ม (บล็อก)", "amber"),
            ("⚠️", "ออเดอร์ยกเลิก", f"{odd:,} รายการ", f"ตัดทิ้ง {cut:,} · คงไว้ {len(kept) if kept is not None else 0:,}", "purple"),
        ])


def _result_charts(lines):

    import plotly.graph_objects as go

    o = lines.drop_duplicates("เลขที่ออเดอร์").copy()
    t = pd.to_datetime(o["วันที่พิมพ์"], format="%d/%m/%Y %H:%M", errors="coerce")

    multi = t.dt.date.nunique() > 1

    o["_k"] = t.dt.strftime("%d/%m") if multi else t.dt.hour.map(lambda h: "" if pd.isna(h) else f"{int(h):02d}:00")
    o["_s"] = t.dt.strftime("%Y%m%d%H") if multi else t.dt.hour

    g = (
        o.dropna(subset=["_k"]).groupby(["_s", "_k"], as_index=False)
        .agg(ออเดอร์=("เลขที่ออเดอร์", "nunique"), ยอดขาย=("ยอดขาย", "sum"))
        .sort_values("_s")
    )

    left, right = st.columns([3, 2])

    with left:
        with card("od_chart_day"):

            section_title("จำนวนออเดอร์และยอดขาย" + ("รายวัน" if multi else "รายชั่วโมง"))

            fig = go.Figure()
            fig.add_bar(x=g["_k"], y=g["ออเดอร์"], name="จำนวนออเดอร์", marker_color="#2563eb")
            fig.add_scatter(x=g["_k"], y=g["ยอดขาย"], name="ยอดขาย", yaxis="y2",
                            mode="lines+markers", line=dict(color="#16a34a", width=2))
            fig.update_layout(
                height=300, margin=dict(l=0, r=0, t=10, b=0),
                yaxis=dict(title="ออเดอร์"), yaxis2=dict(title="ยอดขาย (บาท)", overlaying="y", side="right"),
                legend=dict(orientation="h", y=1.12), plot_bgcolor="white", paper_bgcolor="white",
            )
            st.plotly_chart(fig, use_container_width=True)

    with right:
        with card("od_chart_carrier"):

            section_title("ยอดขายตามขนส่ง")

            o["_c"] = [_carrier_of(x)[0] for x in o["ขนส่ง"]]
            c = o.groupby("_c", as_index=False)["ยอดขาย"].sum().sort_values("ยอดขาย", ascending=False)

            fig2 = px.pie(c, names="_c", values="ยอดขาย", hole=0.62,
                          color_discrete_sequence=["#2563eb", "#16a34a", "#f59e0b", "#ef4444", "#8b5cf6", "#94a3b8"])
            fig2.update_traces(textinfo="percent")
            fig2.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="white",
                               legend=dict(orientation="v", x=1.0, y=0.5))
            st.plotly_chart(fig2, use_container_width=True)


def _render_api_mode():

    stage = st.session_state.get(STAGE_KEY, "home")

    if stage == "home":
        _home_view()
        return

    if stage == "setup":
        _setup_view()
        return

    api = st.session_state.get(API_KEY)

    if not api:
        _go("setup")
        return

    files = st.session_state.setdefault(API_FILES_KEY, {})
    lines, info = api["lines"], api["info"]

    compare, online, call = _express_values(files)

    _result_header(api, files, compare)

    if info["warnings"]:
        st.warning("\n".join(f"- {w}" for w in info["warnings"]))

    # รหัสสินค้าของ Express (ไว้ตัดตัวนำหน้ารหัสฝั่ง Shipnity ให้ตรงกัน)
    known = set()

    if compare:

        for data, name in ((online, "Online"), (call, "Call Center")):

            if data:
                known |= set(
                    _parse_csv_items(_csv_lines(data), name)["รหัสสินค้า"].map(_inv_norm_code)
                )

    pair_stats = None
    variance = None

    if compare and (online or call):

        csv_orders = pd.concat(
            [
                _parse_invoice_report(_csv_lines(data), name)
                for data, name in ((online, "Online"), (call, "Call Center")) if data
            ],
            ignore_index=True
        )

        lines, pair_stats = sp.assign_invoices(lines, csv_orders)

        pre_total = lines.drop_duplicates("เลขที่ออเดอร์")["ยอดขาย"].sum()

        lines, restored = sp.restore_cancelled(lines, info.get("all_lines"), csv_orders)

        _items_for_move = pd.concat(
            [
                _parse_csv_items(_csv_lines(data), name)
                for data, name in ((online, "Online"), (call, "Call Center")) if data
            ],
            ignore_index=True
        )

        lines, moved = sp.rebalance_blocks(lines, csv_orders, _items_for_move, known)

        if len(moved):
            with st.expander(f"🔀 ย้ายออเดอร์ที่ Express ลงบิลคนละกลุ่มกับที่แอปจัด ({len(moved):,} ออเดอร์)", expanded=True):
                st.caption(
                    "ใบกำกับสองใบต่างจาก CSV เท่ากันแต่ตรงข้ามกัน (+X / −X) แอปจึงย้ายออเดอร์ที่ยอดรวมเท่าส่วนต่างไปอยู่บิลที่ Express ลงจริง "
                    "ดูคอลัมน์ขนส่งว่าเป็นขนส่งอะไร — ถ้าซ้ำแบบเดิมทุกวัน ให้แก้กฎใน CUSTOMER_RULES"
                )
                st.dataframe(moved, use_container_width=True, hide_index=True)

        csv_items = pd.concat(
            [
                _parse_csv_items(_csv_lines(data), name)
                for data, name in ((online, "Online"), (call, "Call Center")) if data
            ],
            ignore_index=True
        )

        rec = au.reconcile(lines, csv_orders, csv_items, restored, pair_stats.get("methods"), known)
        bdf, bsum = au.variance_bridge(rec, pre_total)
        variance = (rec, bdf, bsum)

        all_l = info.get("all_lines")

        if all_l is not None and "ยกเลิก" in all_l.columns and all_l["ยกเลิก"].any():

            with st.expander("🚫 ผลตรวจออเดอร์ยกเลิก (เทียบกับใบกำกับ Express)", expanded=bool(len(restored))):
                _cancelled_table(all_l, restored, checked=True)

    try:
        promo = _promo_bytes(lines, frozenset(known))
        res = _invoice_compare(promo, online, call)
        lines_df, orders_df = _build_order_detail(promo)
    except Exception as e:  # noqa: BLE001
        st.error(f"ประมวลผลข้อมูลไม่ได้: {e}")
        return

    def _notes():

        st.caption(
            "รหัสสินค้าจาก Shipnity ตัดตัวนำหน้าแล้ว เช่น N_W1M_FM18 → W1M_FM18"
            + (" (ตรวจกับรหัสใน Express ด้วย)" if known else "")
        )

        if pair_stats:

            st.caption(
                "จับคู่บล็อกกับใบกำกับ CSV: ยอดตรงกัน "
                f"{pair_stats['exact']:,} · จับตามลำดับ {pair_stats['by_order']:,} · "
                f"บล็อกที่ไม่มีใบกำกับ {pair_stats['blocks_unpaired']:,} · "
                f"ใบกำกับที่ไม่มีบล็อก {pair_stats['invoices_unpaired']:,}"
            )

        _mapping_check(lines, info)

    _result_kpis(lines, info, res if compare else None, compare)

    _result_charts(lines)

    _fetch_summary(lines, info)

    if not compare:

        t1, t2 = st.tabs(["📊 ภาพรวม", "🔎 ค้นหาออเดอร์"])

        with t1:
            _shipnity_overview(res)

        with t2:
            _tab_orders(None, orders_df, lines_df)

        _notes()

        return

    if variance:
        _variance_card(*variance)

    _compare_tabs(res, orders_df, lines_df, promo, online, call)

    _notes()


def render_order_detail_page():

    stage = st.session_state.get(STAGE_KEY, "home")

    page_header(
        "🔎",
        "รายละเอียดออเดอร์",
        "เทียบใบกำกับ Express (Online / Call Center) กับ Shipnity โปรโมชั่น "
        "โดยดึงจาก Shipnity โดยตรง หรืออัปโหลดไฟล์แบบเดิม"
    )

    if stage == "file":

        if st.button("← กลับหน้าหลัก", key="od_file_back"):
            _go("home")

        _render_upload_mode()

        return

    _render_api_mode()