"""หน้า "ไฟล์งาน" — ดึงออเดอร์จาก Shipnity (GraphQL) แล้ววิเคราะห์เชิงลึก

แหล่งข้อมูล:
    🔌 ดึงจาก Shipnity   เลือกช่วงวันที่ → ดึงผ่าน shipnity_api.py (ค่าเริ่มต้น)
    📁 อัปโหลดไฟล์       ไฟล์ .xlsx ที่ส่งออกจาก Shipnity (สำรอง เช่น Cookie หมดอายุ)
ทั้งสองแบบแปลงเป็นตารางเดียวกัน แท็บด้านล่างจึงใช้ร่วมกัน

แท็บ:
    📊 ช่องทาง & ประเภท  ออเดอร์แต่ละช่องทาง แยกประเภท (Call Center / Online Marketing)
    🚚 ขนส่ง             แต่ละช่องทาง/ประเภท ใช้ขนส่งอะไร
    🧾 ออเดอร์ / รหัส    เลขที่ออเดอร์ + รหัส (จากหมายเหตุ) + SET / จำนวน
    👥 ลูกค้า & พื้นที่  รหัสลูกค้าที่ซื้อเยอะ + จังหวัดที่ซื้อเยอะ
    💡 Insight           ตรวจข้อมูลเชิงลึก หาจุดที่ต้องตรวจสอบ
"""

import datetime as dt
import io
import os
import re
import uuid

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from backend import shipnity_api as sn
    SN_ERROR = ""
except ImportError as e:  # ลืมคัดลอก shipnity_api.py ไว้โฟลเดอร์เดียวกับ app.py (หรือขาด requests)
    sn = None
    SN_ERROR = str(e)

from backend.channel import classify_channel
from frontend.ui import page_header
from frontend.shipnity_widgets import (
    pick_period as _pick_period,
    secrets as _secrets,
    today_th as _today_th,
)
from backend.work_files_logic import (  # noqa: E402
    COL_ORDER,
    COL_SALES,
    COL_CH,
    COL_SHIP,
    COL_BANK,
    COL_NOTE,
    COL_CUST,
    COL_NAME,
    COL_PHONE,
    COL_DISC,
    COL_CREATED,
    COL_ADDR,
    COL_CANCEL,
    REQUIRED,
    MARKET,
    PAID_BANKS,
    NOTE_RE,
    PO_RE,
    PROVINCES,
    PROV_BY_LEN,
    PROV_TAG_RE,
    BKK_RE,
    _norm_channel,
    _page_name,
    _province,
    _parse_note,
    _code_kind,
    _find_col,
    _prepare,
    _load,
    _summ,
    _first_valid,
    _insights,
    _money,
)


_load = st.cache_data(show_spinner=False)(_load)

FILES_KEY = "work_files"
UPLOADER_N_KEY = "work_files_uploader_n"
RESULT_KEY = "work_files_result"

# ---- ชื่อคอลัมน์ในไฟล์ Shipnity ----






# =========================================================
# เตรียมข้อมูล
# =========================================================

















# =========================================================
# ชิ้นส่วนแสดงผล
# =========================================================





def _show(df, **kw):

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ยอดขาย": st.column_config.NumberColumn(format="%.2f"),
            "เฉลี่ย/ออเดอร์": st.column_config.NumberColumn(format="%.2f"),
        },
        **kw
    )


def _order_cols(df):

    cols = [
        COL_ORDER, "ช่องทาง", "ประเภท", "ขนส่ง", "การชำระ",
        "รหัส (หมายเหตุ)", "ชนิดรหัส", "SET", "อ้างอิง PO",
    ]

    if df["จำนวน"].notna().any():
        cols.append("จำนวน")

    cols.append(COL_SALES)

    return df[cols]


# =========================================================
# แท็บ: ช่องทาง & ประเภท
# =========================================================

def _tab_channel(df):

    c = st.columns(4)

    c[0].metric("ออเดอร์", f"{len(df):,}")
    c[1].metric("ยอดขายรวม", _money(df[COL_SALES].sum()))
    c[2].metric("เฉลี่ย/ออเดอร์", _money(df[COL_SALES].mean()))
    c[3].metric("สัดส่วน COD", f"{df['COD'].mean() * 100:.0f}%")

    g = _summ(df, ["ช่องทาง", "ประเภท"])

    fig = px.bar(
        g, x="ช่องทาง", y="ออเดอร์", color="ประเภท",
        barmode="stack", text_auto=True, title="จำนวนออเดอร์ตามช่องทาง แยกประเภท"
    )

    st.plotly_chart(fig, use_container_width=True)

    _show(g)

    st.markdown("#### รายละเอียดรายช่องทาง")

    ch = st.selectbox(
        "เลือกช่องทาง",
        sorted(df["ช่องทาง"].unique()),
        key="wf_channel"
    )

    sub = df[df["ช่องทาง"] == ch]

    st.caption("แยกประเภท → ขนส่ง")
    _show(_summ(sub, ["ประเภท", "ขนส่ง"]))

    pages = sub[sub["เพจ/แบรนด์"] != ""]

    if not pages.empty:
        st.caption("เพจ/แบรนด์ที่ลูกค้าทักมา (Top 10)")
        _show(_summ(pages, ["เพจ/แบรนด์"]).head(10))

    with st.expander(f"รายการออเดอร์ของ {ch} ({len(sub):,})"):
        _show(_order_cols(sub))


# =========================================================
# แท็บ: ขนส่ง
# =========================================================

def _tab_carrier(df):

    g = _summ(df, ["ขนส่ง", "ช่องทาง"])

    fig = px.bar(
        g, x="ขนส่ง", y="ออเดอร์", color="ช่องทาง",
        barmode="stack", title="ขนส่งที่ใช้ แยกตามช่องทาง"
    )

    st.plotly_chart(fig, use_container_width=True)

    st.caption("สรุปตามขนส่ง")
    _show(_summ(df, ["ขนส่ง", "การชำระ"]))

    st.caption("ขนส่ง × ประเภท (จำนวนออเดอร์)")

    st.dataframe(
        pd.crosstab(df["ขนส่ง"], df["ประเภท"], margins=True, margins_name="รวม"),
        use_container_width=True
    )

    car = st.selectbox("ดูออเดอร์ของขนส่ง", sorted(df["ขนส่ง"].unique()), key="wf_carrier")

    _show(_order_cols(df[df["ขนส่ง"] == car]))


# =========================================================
# แท็บ: ออเดอร์ / รหัส / จำนวน
# =========================================================

def _tab_orders(df):

    f1, f2, f3, f4 = st.columns(4)

    chs = f1.multiselect("ช่องทาง", sorted(df["ช่องทาง"].unique()), key="wf_f_ch")
    typ = f2.multiselect("ประเภท", sorted(df["ประเภท"].unique()), key="wf_f_type")
    car = f3.multiselect("ขนส่ง", sorted(df["ขนส่ง"].unique()), key="wf_f_car")
    q = f4.text_input("ค้นหาเลขที่ออเดอร์ / รหัส", key="wf_f_q").strip().upper()

    v = df

    if chs:
        v = v[v["ช่องทาง"].isin(chs)]
    if typ:
        v = v[v["ประเภท"].isin(typ)]
    if car:
        v = v[v["ขนส่ง"].isin(car)]
    if q:
        v = v[
            v[COL_ORDER].str.upper().str.contains(q, regex=False)
            | v["รหัส (หมายเหตุ)"].str.contains(q, regex=False)
        ]

    st.caption(f"{len(v):,} ออเดอร์ | ยอดขาย {_money(v[COL_SALES].sum())}")

    out = _order_cols(v)

    _show(out)

    st.download_button(
        "⬇️ ดาวน์โหลดตารางนี้ (CSV)",
        data=out.to_csv(index=False).encode("utf-8-sig"),
        file_name="orders_cleaned.csv",
        mime="text/csv",
        key="wf_dl_orders"
    )

    st.markdown("#### รหัสพนักงานที่ขายสินค้า (จำนวนออเดอร์ / จำนวนชิ้น)")

    coded = v[v["รหัส (หมายเหตุ)"] != ""]

    if coded.empty:
        st.info("ไม่พบรหัสในหมายเหตุของออเดอร์ที่เลือก")
        return

    agg = {
        "จำนวนออเดอร์": (COL_ORDER, "count"),
        "ยอดขาย": (COL_SALES, "sum"),
    }

    if coded["จำนวน"].notna().any():
        agg["จำนวนชิ้น"] = ("จำนวน", "sum")

    s = (
        coded.groupby(["รหัส (หมายเหตุ)", "ชนิดรหัส"])
        .agg(**agg)
        .reset_index()
        .sort_values("จำนวนออเดอร์", ascending=False)
    )

    _show(s)

    if not coded["จำนวน"].notna().any():
        st.caption(
            "ไฟล์นี้ไม่มีคอลัมน์จำนวนชิ้น จึงนับเป็น “จำนวนออเดอร์” "
            "และรหัส VX/VP/OB ดึงจากหมายเหตุ ยังไม่ยืนยันว่าเป็นรหัสสินค้า"
        )


# =========================================================
# แท็บ: ลูกค้า & พื้นที่
# =========================================================



def _tab_customer_area(df):

    d = df[~df["ยกเลิก"] & df[COL_CUST].notna()]

    if d.empty:
        st.info("ไม่มีข้อมูลรหัสลูกค้า")
        return

    # ---------- สรุปรายลูกค้า ----------
    cust = (
        d.groupby(COL_CUST)
        .agg(
            ชื่อ=(COL_NAME, _first_valid),
            จังหวัด=("จังหวัด", lambda x: _first_valid(x[x != "ไม่ระบุที่อยู่"])),
            ช่องทาง=("ช่องทาง", lambda x: ", ".join(sorted(set(x)))),
            ออเดอร์=(COL_ORDER, "count"),
            ยอดขาย=(COL_SALES, "sum"),
        )
        .reset_index()
        .rename(columns={COL_CUST: "รหัสลูกค้า"})
    )

    c = st.columns(4)

    c[0].metric("ลูกค้า (รหัส)", f"{len(cust):,}")
    c[1].metric("ลูกค้าซื้อซ้ำ (>1 ออเดอร์)", f"{(cust['ออเดอร์'] > 1).sum():,}")
    c[2].metric("ยอดสูงสุด/ลูกค้า", _money(cust["ยอดขาย"].max()))
    c[3].metric(
        "ไม่ทราบจังหวัด",
        f"{(d['จังหวัด'] == 'ไม่ระบุที่อยู่').sum():,} ออเดอร์",
    )

    # ---------- ลูกค้าที่ซื้อเยอะ ----------
    st.markdown("#### รหัสลูกค้าที่ซื้อเยอะ")

    f1, f2 = st.columns(2)

    by = f1.radio(
        "จัดอันดับตาม", ["ยอดขาย", "จำนวนออเดอร์"],
        horizontal=True, key="wf_cu_by"
    )
    top_n = f2.slider("แสดง Top", 5, 50, 15, key="wf_cu_n")

    sort_cols = ["ยอดขาย", "ออเดอร์"] if by == "ยอดขาย" else ["ออเดอร์", "ยอดขาย"]

    top = cust.sort_values(sort_cols, ascending=False).head(top_n)

    _show(top)

    st.download_button(
        "⬇️ ดาวน์โหลดลูกค้าทั้งหมด (CSV)",
        data=cust.sort_values(sort_cols, ascending=False)
        .to_csv(index=False).encode("utf-8-sig"),
        file_name="customers_summary.csv",
        mime="text/csv",
        key="wf_dl_cust"
    )

    # ---------- พื้นที่ ----------
    st.markdown("#### พื้นที่ที่ซื้อเยอะ (ตามจังหวัด)")

    known = d[d["จังหวัด"] != "ไม่ระบุที่อยู่"]

    prov = (
        known.groupby("จังหวัด")
        .agg(
            ออเดอร์=(COL_ORDER, "count"),
            ลูกค้า=(COL_CUST, "nunique"),
            ยอดขาย=(COL_SALES, "sum"),
        )
        .reset_index()
    )

    prov["เฉลี่ย/ออเดอร์"] = (prov["ยอดขาย"] / prov["ออเดอร์"]).round(2)
    prov["% ยอดขาย"] = (
        prov["ยอดขาย"] / max(prov["ยอดขาย"].sum(), 1) * 100
    ).round(1)

    metric = st.radio(
        "ดูตาม", ["ยอดขาย", "ออเดอร์"], horizontal=True, key="wf_cu_pm"
    )

    prov = prov.sort_values(metric, ascending=False)

    fig = px.bar(
        prov.head(15), x="จังหวัด", y=metric, text_auto=",.0f",
        title=f"Top 15 จังหวัด ตาม{metric}"
    )

    st.plotly_chart(fig, use_container_width=True)

    _show(prov)

    st.caption(
        f"ระบุจังหวัดได้ {len(known):,} จาก {len(d):,} ออเดอร์ "
        "(ออเดอร์ที่ไม่มีที่อยู่ เช่น Lazada / Shopee COD ไม่ถูกนับ)"
    )

    # ---------- ลูกค้าในจังหวัด ----------
    p = st.selectbox("ดูลูกค้าในจังหวัด", prov["จังหวัด"].tolist(), key="wf_cu_prov")

    _show(
        cust[cust["จังหวัด"] == p]
        .sort_values(["ยอดขาย", "ออเดอร์"], ascending=False)
    )


# =========================================================
# แท็บ: Insight
# =========================================================



def _tab_insight(df):

    items = _insights(df)

    c = st.columns(3)

    c[0].metric("🔴 ควรแก้", sum(i[0] == "🔴" for i in items))
    c[1].metric("🟡 ควรตรวจ", sum(i[0] == "🟡" for i in items))
    c[2].metric("🔵 ข้อมูลประกอบ", sum(i[0] == "🔵" for i in items))

    for level, title, detail, sub in items:

        with st.expander(f"{level} {title}"):

            st.caption(detail)

            if COL_ORDER in sub.columns and "ช่องทาง" in sub.columns \
                    and "ประเภท" in sub.columns:
                sub = _order_cols(sub)

            _show(sub)


# =========================================================
# แหล่งข้อมูล: ดึงจาก Shipnity (API)
# =========================================================

SOURCE_API = "🔌 ดึงจาก Shipnity"
SOURCE_FILE = "📁 อัปโหลดไฟล์ (สำรอง)"

SETUP_HELP = """
**ตั้งค่าครั้งแรก (ทำครั้งเดียว)**

1. เปิด Shipnity ในเบราว์เซอร์ที่ล็อกอินอยู่ กด **F12** → แท็บ **Network** → ค้นหา `graphql`
   แล้วเปิดหน้ารายการออเดอร์ให้โหลด
2. คลิกรายการ `graphql` ที่คำตอบมีออเดอร์ (`dataWorksheetSearch`) → แท็บ **Payload**
   → คัดลอก JSON ทั้งก้อนไปบันทึกเป็น **`shipnity_request.json`** ไว้โฟลเดอร์เดียวกับ `app.py`
3. ในไฟล์นั้น แทนเลขหน้าด้วย `"{{page}}"` เช่น `"page": "{{page}}"`
   (หรือเขียน `{{page}}` ในข้อความ query ถ้าเลขหน้าอยู่ตรงนั้น)
4. แท็บ **Headers** → *Request Headers* → คัดลอกค่า **cookie** มาวางในช่องด้านบน
   (ใส่ถาวรได้ที่ `.streamlit/secrets.toml` ใต้หัวข้อ `[shipnity]` ห้ามส่งขึ้น git)

Cookie จะหมดอายุตามเวลาของ Shipnity ถ้าขึ้นว่า “ปฏิเสธการเข้าถึง” ให้คัดลอกค่าใหม่
"""










def _source_api():

    if sn is None:

        st.error(
            f"โหลดโมดูล shipnity_api ไม่ได้ ({SN_ERROR}) — คัดลอกไฟล์ `shipnity_api.py` "
            "ไปไว้โฟลเดอร์เดียวกับ `app.py` (ถ้าขาด requests ให้รัน `pip install requests`) "
            "แล้วรีเฟรชหน้านี้"
        )

        st.info("ระหว่างนี้ใช้ช่อง “📁 อัปโหลดไฟล์ (สำรอง)” ด้านล่างเพื่อใช้งานต่อได้")

        return

    secrets = _secrets()
    today = _today_th()

    cfg = sn.build_config(secrets)

    problems = sn.config_problems(cfg)

    period = _pick_period(today)

    if period is None:
        return

    d1, d2 = period

    days = (d2 - d1).days + 1

    # เพดานจำนวนหน้าอัตโนมัติ: เผื่อ ≈45 หน้า/วัน (วันที่ตรวจ ≈30 หน้า/วัน, หน้าละ ≈14 ออเดอร์)
    auto_cap = min(5000, max(60, ((today - d1).days + 1) * 45))

    with st.expander("ขั้นสูง"):

        override = st.number_input(
            "จำนวนหน้าสูงสุด (0 = อัตโนมัติ)",
            min_value=0, max_value=5000, value=0, step=50,
            key="wf_max_pages"
        )

    max_pages = int(override) or auto_cap

    r1, r2 = st.columns([4, 1.5], vertical_alignment="center")

    with r1:

        if days > 31:
            st.warning(
                f"ช่วงยาว {days:,} วัน อาจใช้เวลานานหลายนาที และอาจชนเพดานจำนวนหน้า "
                "— ถ้าไม่จำเป็นให้เลือกช่วงสั้นลง"
            )

    with r2:
        run = st.button(
            "🔄 ดึงข้อมูล",
            type="primary",
            use_container_width=True,
            key="wf_fetch"
        )

    if not run:

        for p in problems:
            st.info(p)

        return

    if problems:

        for p in problems:
            st.error(p)

        return

    bar = st.progress(0.0, text="กำลังเชื่อมต่อ Shipnity...")

    def on_page(n, oldest):
        bar.progress(
            min(n / int(max_pages), 1.0),
            text=f"ดึงแล้ว {n:,} หน้า · ออเดอร์เก่าสุด {oldest:%d/%m/%Y %H:%M}"
        )

    try:

        raw, info = sn.fetch_orders(
            cfg, d1, d2, max_pages=int(max_pages), progress=on_page
        )

        df = _prepare(raw) if not raw.empty else None

    except sn.ShipnityError as e:
        bar.empty()
        st.error(str(e))
        return

    except Exception as e:  # noqa: BLE001
        bar.empty()
        st.error(f"ดึงข้อมูลไม่สำเร็จ: {type(e).__name__}: {e}")
        return

    bar.empty()

    if df is None:

        st.session_state.pop(RESULT_KEY, None)

        st.warning("ไม่พบออเดอร์ที่สร้างในช่วงวันที่ที่เลือก")

        for w in info["warnings"]:
            st.warning(w)

        return

    label = f"Shipnity API · {d1:%d/%m/%Y}" + (
        f" – {d2:%d/%m/%Y}" if d2 != d1 else ""
    )

    st.session_state[RESULT_KEY] = {
        "name": label,
        "df": df,
        "time": dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "info": info,
    }


# =========================================================
# แหล่งข้อมูล: อัปโหลดไฟล์ (สำรอง)
# =========================================================

def _source_file():

    files = st.session_state.setdefault(FILES_KEY, [])
    n = st.session_state.setdefault(UPLOADER_N_KEY, 0)

    # ---------- อัปโหลด + ปุ่มประมวลผล (อยู่ข้างกัน) ----------
    c1, c2 = st.columns([4, 1], vertical_alignment="bottom")

    with c1:
        uploaded = st.file_uploader(
            "อัปโหลดไฟล์ Shipnity (.xlsx) — เลือกได้หลายไฟล์",
            accept_multiple_files=True,
            key=f"work_files_uploader_{n}"
        )

    with c2:
        run = st.button(
            "🚀 ประมวลผล",
            type="primary",
            use_container_width=True,
            key="wf_run"
        )

    if uploaded:

        existing = {(f["name"], f["size"]) for f in files}

        for f in uploaded:

            data = f.getvalue()

            if (f.name, len(data)) in existing:
                continue

            files.append(
                {
                    "id": uuid.uuid4().hex,
                    "name": f.name,
                    "size": len(data),
                    "data": data,
                    "time": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
                }
            )

        st.session_state[UPLOADER_N_KEY] = n + 1
        st.rerun()

    excel = [
        f for f in files
        if f["name"].lower().endswith((".xlsx", ".xls"))
    ]

    if excel:
        st.caption("ไฟล์ที่อัปโหลดแล้ว: " + ", ".join(f["name"] for f in excel))

    # ---------- ประมวลผลเมื่อกดปุ่ม (ใช้ไฟล์ Shipnity ล่าสุดที่อ่านได้) ----------
    if not run:
        return

    if not excel:
        st.warning("อัปโหลดไฟล์ Shipnity (.xlsx) ก่อนกดประมวลผล")
        return

    res, errs = None, []

    with st.spinner("กำลังประมวลผล..."):

        for f in reversed(excel):

            d, err = _load(f["data"])

            if d is not None:

                res = {
                    "name": f["name"],
                    "df": d,
                    "time": dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                }

                break

            errs.append(f"{f['name']}: {err}")

    if res is None:
        st.session_state.pop(RESULT_KEY, None)
        st.error("ประมวลผลไม่ได้ — " + " | ".join(errs))
        return

    st.session_state[RESULT_KEY] = res


# =========================================================
# หน้าหลัก
# =========================================================

def _show_result():

    res = st.session_state.get(RESULT_KEY)

    if res is None:
        return

    st.caption(f"{res['name']} · {len(res['df']):,} ออเดอร์ · {res['time']}")

    info = res.get("info")

    if info:

        for w in info["warnings"]:
            st.warning(w)

    df = res["df"]

    tabs = st.tabs(
        [
            "📊 ช่องทาง & ประเภท",
            "🚚 ขนส่ง",
            "🧾 ออเดอร์ / รหัส / จำนวน",
            "👥 ลูกค้า & พื้นที่",
            "💡 Insight",
        ]
    )

    for tab, fn in zip(
        tabs,
        [_tab_channel, _tab_carrier, _tab_orders, _tab_customer_area, _tab_insight],
    ):
        with tab:
            fn(df)


def render_work_files_page():

    page_header(
        "🗂️",
        "ไฟล์งาน",
        "ดึงออเดอร์จาก Shipnity เพื่อดูรายช่องทาง ขนส่ง รหัส ลูกค้า/พื้นที่ และ insight เชิงลึก"
    )

    _source_api()

    _show_result()

    with st.expander("📁 อัปโหลดไฟล์แทนการดึงจาก Shipnity (สำรอง)", expanded=sn is None):
        _source_file()


