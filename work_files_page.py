"""หน้า "ไฟล์งาน" — อัปโหลดไฟล์ Shipnity แล้ววิเคราะห์เชิงลึก

แท็บ:
    📊 ช่องทาง & ประเภท  ออเดอร์แต่ละช่องทาง แยกประเภท (Call Center / Online Marketing)
    🚚 ขนส่ง             แต่ละช่องทาง/ประเภท ใช้ขนส่งอะไร
    🧾 ออเดอร์ / รหัส    เลขที่ออเดอร์ + รหัส (จากหมายเหตุ) + SET / จำนวน
    💡 Insight           ตรวจข้อมูลเชิงลึก หาจุดที่ต้องตรวจสอบ
"""

import datetime as dt
import io
import re
import uuid

import pandas as pd
import plotly.express as px
import streamlit as st

from channel import classify_channel
from ui import page_header

FILES_KEY = "work_files"
UPLOADER_N_KEY = "work_files_uploader_n"
RESULT_KEY = "work_files_result"

# ---- ชื่อคอลัมน์ในไฟล์ Shipnity ----
COL_ORDER = "เลขที่ออเดอร์"
COL_SALES = "ยอดขาย"
COL_CH = "ช่องทางที่ลูกค้าทักมา"
COL_SHIP = "ขนส่ง"
COL_BANK = "ธนาคารที่รับเงิน"
COL_NOTE = "หมายเหตุ"
COL_CUST = "รหัสลูกค้า (ลูกค้า)"
COL_NAME = "ชื่อ (ลูกค้า)"
COL_PHONE = "เบอร์โทร (ลูกค้า)"
COL_DISC = "ส่วนลดจาก Marketplace"
COL_CREATED = "วันที่สร้าง"
REQUIRED = [COL_ORDER, COL_SALES, COL_CH, COL_SHIP]

MARKET = ["Shopee", "TikTok", "Lazada"]
PAID_BANKS = ["กสิกร", "กรุงเทพ", "กรุงไทย", "บัตรเครดิต", "Paysbuy"]

NOTE_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*,\s*([^,]*),\s*([^,]*)")
PO_RE = re.compile(r"PO\.[A-Za-z0-9]+")


# =========================================================
# เตรียมข้อมูล
# =========================================================

def _norm_channel(s):

    t = str(s).strip().lower()

    for key, name in [
        ("fb", "Facebook"),
        ("facebook", "Facebook"),
        ("shopee", "Shopee"),
        ("tiktok", "TikTok"),
        ("lazada", "Lazada"),
        ("line", "Line"),
        ("phone", "โทรศัพท์"),
    ]:
        if t.startswith(key):
            return name

    return "อื่นๆ"


def _page_name(s):

    s = str(s)

    return s.split(":", 1)[1].strip() if ":" in s else ""


def _parse_note(note):
    """หมายเหตุรูปแบบ  วันที่,SETn,รหัส,-,PO.xxx,ข้อความ"""

    out = {
        "วันที่ในหมายเหตุ": pd.NaT,
        "SET": "",
        "รหัส (หมายเหตุ)": "",
        "อ้างอิง PO": "",
    }

    s = "" if pd.isna(note) else str(note)

    m = NOTE_RE.match(s)

    if m:

        d, mo, y = int(m[1]), int(m[2]), int(m[3])

        y = y + 2500 if y < 100 else y
        y = y - 543 if y > 2400 else y

        try:
            out["วันที่ในหมายเหตุ"] = pd.Timestamp(y, mo, d)
        except ValueError:
            pass

        if re.fullmatch(r"SET\d+", m[4].strip(), re.I):
            out["SET"] = m[4].strip().upper()

        code = m[5].strip().upper()

        if re.fullmatch(r"VX\w+|VP\d+|OB\d+", code):
            out["รหัส (หมายเหตุ)"] = code

    p = PO_RE.search(s)

    if p:
        out["อ้างอิง PO"] = p.group(0)

    return out


def _code_kind(code):

    if code.startswith(("VP", "OB")):
        return "รหัสพนักงาน (VP/OB)"

    if code.startswith("VX"):
        return "รหัส VX"

    return ""


def _find_col(df, keywords):

    for c in df.columns:
        if any(k in str(c).lower() for k in keywords):
            return c

    return None


def _prepare(raw):

    df = raw.copy()

    for c in [COL_NOTE, COL_BANK, COL_CUST, COL_NAME, COL_PHONE, COL_DISC]:
        if c not in df.columns:
            df[c] = pd.NA

    df[COL_ORDER] = df[COL_ORDER].astype(str).str.strip()
    df[COL_SALES] = pd.to_numeric(df[COL_SALES], errors="coerce").fillna(0)
    df[COL_DISC] = pd.to_numeric(df[COL_DISC], errors="coerce").fillna(0)

    df["ช่องทาง"] = df[COL_CH].map(_norm_channel)
    df["เพจ/แบรนด์"] = df[COL_CH].map(_page_name)
    df["ประเภท"] = classify_channel(df, COL_CH)["Channel_Category"]

    df["ขนส่ง"] = df[COL_SHIP].fillna("(ไม่ระบุ)").astype(str).str.strip()
    df["ธนาคาร"] = df[COL_BANK].fillna("-").astype(str).str.strip()
    df["COD"] = df["ขนส่ง"].str.contains("COD", case=False)
    df["การชำระ"] = df["COD"].map(
        {True: "COD (เก็บเงินปลายทาง)", False: "ไม่ใช่ COD"}
    )

    df["กลุ่มเลขที่"] = df[COL_ORDER].str.extract(r"^([A-Za-z]+)")[0]

    df["วันที่สร้าง_dt"] = pd.to_datetime(
        df[COL_CREATED] if COL_CREATED in df.columns else pd.NaT,
        format="%d/%m/%Y %H:%M",
        errors="coerce"
    )

    parsed = pd.DataFrame(
        df[COL_NOTE].map(_parse_note).tolist(),
        index=df.index
    )

    df = pd.concat([df, parsed], axis=1)

    df["ชนิดรหัส"] = df["รหัส (หมายเหตุ)"].map(_code_kind)

    # ถ้าไฟล์มีคอลัมน์รหัสสินค้า/จำนวนจริง ให้ใช้แทน
    pcol = _find_col(df, ["รหัสสินค้า", "sku", "product_code"])

    if pcol is not None:
        df["รหัส (หมายเหตุ)"] = df[pcol].fillna("").astype(str)
        df["ชนิดรหัส"] = "รหัสสินค้า"

    qcol = _find_col(df, ["จำนวน", "qty", "quantity"])

    df["จำนวน"] = (
        pd.to_numeric(df[qcol], errors="coerce") if qcol is not None else pd.NA
    )

    return df


@st.cache_data(show_spinner=False)
def _load(data):

    try:
        raw = pd.read_excel(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        return None, f"อ่านไฟล์ไม่ได้: {e}"

    missing = [c for c in REQUIRED if c not in raw.columns]

    if missing:
        return None, "ไม่ใช่ไฟล์ Shipnity (ขาดคอลัมน์: " + ", ".join(missing) + ")"

    if raw.empty:
        return None, "ไม่มีข้อมูล (มีแต่หัวคอลัมน์)"

    return _prepare(raw), None


# =========================================================
# ชิ้นส่วนแสดงผล
# =========================================================

def _money(x):
    return f"{x:,.0f}"


def _summ(df, by):

    g = (
        df.groupby(by, dropna=False)
        .agg(ออเดอร์=(COL_ORDER, "count"), ยอดขาย=(COL_SALES, "sum"))
        .reset_index()
    )

    g["เฉลี่ย/ออเดอร์"] = (g["ยอดขาย"] / g["ออเดอร์"]).round(2)
    g["% ยอดขาย"] = (g["ยอดขาย"] / max(df[COL_SALES].sum(), 1) * 100).round(1)

    return g.sort_values("ยอดขาย", ascending=False)


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

    st.markdown("#### สรุปตามรหัส (จำนวนออเดอร์ / จำนวนชิ้น)")

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
# แท็บ: Insight
# =========================================================

def _insights(df):

    out = []

    def add(level, title, detail, sub):

        if sub is not None and len(sub):
            label = title if level == "🔵" else f"{title} — {len(sub):,} รายการ"
            out.append((level, label, detail, sub))

    non_mkt = ~df["ช่องทาง"].isin(MARKET)

    add("🔴", "ออเดอร์ยอดขาย 0 บาท",
        "ตรวจว่าเป็นของแถม/ตัวอย่าง หรือคีย์ผิด",
        df[df[COL_SALES] <= 0])

    add("🔴", "ไม่ระบุขนส่ง",
        "ออเดอร์ยังไม่มีขนส่ง อาจส่งไม่ได้หรือบันทึกไม่ครบ",
        df[df["ขนส่ง"] == "(ไม่ระบุ)"])

    add("🔴", "เลขที่ออเดอร์ไม่สอดคล้องกับช่องทาง",
        "ขึ้นต้น RE แต่ช่องทางเป็น Marketplace หรือขึ้นต้น M* แต่เป็นช่องทางแชท/โทร",
        df[
            ((df["กลุ่มเลขที่"] == "RE") & df["ช่องทาง"].isin(MARKET))
            | ((df["กลุ่มเลขที่"] != "RE") & non_mkt)
        ])

    d = df[df[COL_CUST].notna()]
    d = d[d.duplicated([COL_CUST, COL_SALES], keep=False)]

    add("🟡", "สงสัยออเดอร์ซ้ำ (ลูกค้ารหัสเดียวกัน ยอดเท่ากัน)",
        "อาจกดสั่งซ้ำ ควรตรวจก่อนส่ง",
        d.sort_values([COL_CUST, COL_SALES]))

    paid_cod = df[non_mkt & df["COD"] & df["ธนาคาร"].isin(PAID_BANKS)]

    add("🔵", f"ขนส่งชื่อ COD แต่ธนาคารระบุรับเงินแล้ว {len(paid_cod):,} ออเดอร์ (แชท/โทร)",
        "พบเป็นจำนวนมากจนน่าจะเป็นชื่อบริการขนส่ง ไม่ใช่ข้อผิดพลาด — "
        "ควรยืนยันกับทีมว่าคอลัมน์ขนส่งกับธนาคารใช้ความหมายนี้ "
        "ก่อนนำยอด COD ไปตามเก็บเงิน",
        paid_cod)

    add("🟡", "ระบุจ่ายทีหลัง/COD แต่ขนส่งไม่ใช่ COD",
        "เฉพาะช่องทางแชท/โทร — อาจเลือกขนส่งผิดประเภท",
        df[non_mkt & ~df["COD"] & df["ธนาคาร"].str.contains("COD|จ่ายทีหลัง", regex=True)])

    add("🟡", "ช่องทางแชท/โทรที่ไม่มีเบอร์โทรลูกค้า",
        "ติดต่อลูกค้าไม่ได้ถ้าส่งไม่สำเร็จ",
        df[non_mkt & df[COL_PHONE].isna()])

    add("🟡", "ออเดอร์รอสินค้าเข้า",
        "หมายเหตุมีคำว่า “รอสินค้าเข้า” — ยอดค้างส่ง",
        df[df[COL_NOTE].astype(str).str.contains("รอสินค้าเข้า")])

    gap = (df["วันที่ในหมายเหตุ"] - df["วันที่สร้าง_dt"].dt.normalize()).dt.days

    add("🟡", "วันที่ในหมายเหตุห่างจากวันสร้างเกิน 7 วัน",
        "อาจเป็นนัดส่ง/วันที่พิมพ์ผิด ควรตรวจ",
        df[gap > 7])

    add("🟡", "วันที่ในหมายเหตุไม่ถูกต้อง (เช่น 00/00/00)",
        "แก้ให้เป็นวันที่จริง",
        df[df[COL_NOTE].astype(str).str.match(r"^\s*00/00")])

    # ---- ข้อมูลเชิงสรุป ----
    top = _summ(df, ["ช่องทาง"]).iloc[0]

    add("🔵", f"ช่องทางยอดขายสูงสุด: {top['ช่องทาง']} ({top['% ยอดขาย']}% ของยอดขาย)",
        "ช่องทางเดียวที่ถือสัดส่วนสูง = ความเสี่ยงพึ่งพาช่องทางเดียว",
        _summ(df, ["ช่องทาง"]))

    cod = df[df["COD"]]

    add("🔵", f"ขนส่งแบบ COD (ตามชื่อขนส่ง) รวม {_money(cod[COL_SALES].sum())} บาท",
        "นับตามชื่อขนส่งเท่านั้น — ยอดที่ต้องเก็บจริงอาจต่ำกว่านี้ "
        "ถ้าบางออเดอร์รับเงินแล้ว (ดูข้อก่อนหน้า)",
        _summ(cod, ["ขนส่ง"]))

    disc = df[df[COL_DISC] > 0]

    add("🔵", f"ส่วนลด Marketplace รวม {_money(disc[COL_DISC].sum())} บาท",
        "ออเดอร์ที่มีส่วนลดจากแพลตฟอร์ม",
        disc[[COL_ORDER, "ช่องทาง", COL_SALES, COL_DISC]])

    return out


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
# หน้าหลัก
# =========================================================

def render_work_files_page():

    page_header(
        "🗂️",
        "ไฟล์งาน",
        "อัปโหลดไฟล์ Shipnity เพื่อดูออเดอร์รายช่องทาง ขนส่ง รหัส และ insight เชิงลึก"
    )

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
    if run:

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

    res = st.session_state.get(RESULT_KEY)

    if res is None:
        st.info("อัปโหลดไฟล์ Shipnity (.xlsx) แล้วกด 🚀 ประมวลผล เพื่อดูผลลัพธ์")
        return

    st.success(
        f"ประมวลผลแล้ว: {res['name']} · {len(res['df']):,} ออเดอร์ · {res['time']}"
    )

    df = res["df"]

    tabs = st.tabs(
        [
            "📊 ช่องทาง & ประเภท",
            "🚚 ขนส่ง",
            "🧾 ออเดอร์ / รหัส / จำนวน",
            "💡 Insight",
        ]
    )

    for tab, fn in zip(
        tabs, [_tab_channel, _tab_carrier, _tab_orders, _tab_insight]
    ):
        with tab:
            fn(df)