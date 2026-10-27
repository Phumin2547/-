"""CSS ของทั้งแอป — แก้สี/หน้าตาที่นี่ที่เดียว"""

import streamlit as st

CSS = """
<style>

:root {
    --navy:#0b1f4d;
    --blue:#2563eb;
    --blue-soft:#eaf1ff;
    --bg:#f3f6fb;
    --border:#e3e9f4;
    --text:#0f172a;
    --muted:#64748b;
    --green:#16a34a;  --green-bg:#e9f8ef;  --green-bd:#bfe8cf;  --green-tx:#15803d;
    --amber:#d97706;  --amber-bg:#fff6e0;  --amber-bd:#f6dca0;  --amber-tx:#b45309;
    --red:#dc2626;    --red-bg:#fdeaea;    --red-bd:#f6c4c4;    --red-tx:#b91c1c;
}

/* ---------- พื้นหลัง / ระยะขอบ ---------- */

.stApp { background: var(--bg); }

[data-testid="stHeader"] { background: transparent; }

.block-container {
    padding: 1.4rem 2.2rem 3rem;
    max-width: 1600px;
}

h1, h2, h3 { letter-spacing: -0.02em; }

/* ---------- Sidebar (เมนูสีกรมท่า) ---------- */

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b1f4d 0%, #0e2a66 100%);
}

/* ดึงหัวข้อ Order Reconciliation ขึ้นชิดบน
   (Streamlit เว้นพื้นที่ด้านบนไว้เยอะให้ปุ่มพับ sidebar) */
[data-testid="stSidebarHeader"] {
    height: 2.4rem !important;
    min-height: 0 !important;
    padding: .6rem .9rem 0 !important;
    margin-bottom: 0 !important;
}

/* ปุ่มพับเมนู « เป็นสีขาว (ให้เห็นชัดบนพื้นกรมท่า) */
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapseButton"] button *,
[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
[data-testid="stSidebarHeader"] button,
[data-testid="stSidebarHeader"] button * {
    color: #ffffff !important;
    fill: #ffffff !important;
    stroke: #ffffff !important;
}

/* แสดงตลอด (Streamlit ซ่อนไว้จนกว่าจะเอาเมาส์ไปวางที่ sidebar) */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarHeader"] button {
    opacity: 1 !important;
    visibility: visible !important;
    display: inline-flex !important;
}

[data-testid="stSidebarCollapseButton"] button:hover,
[data-testid="stSidebarHeader"] button:hover {
    background: rgba(255,255,255,.12) !important;
}

[data-testid="stSidebarUserContent"],
[data-testid="stSidebar"] .block-container {
    padding: .2rem 1rem 1.2rem !important;
    max-width: none;
}

/* แถวเมนูเรียงชิดกันเท่า ๆ กัน */
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: .4rem;
}

[data-testid="stSidebar"] .stButton {
    width: 100%;
}

/* แต่ละเมนู = 1 แถว ความสูงเท่ากัน ข้อความชิดซ้าย */
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    min-height: 2.9rem;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    text-align: left;
    border: 0;
    border-radius: 12px;
    padding: .55rem .95rem;
    background: transparent;
    color: #cbd5e1;
    font-weight: 500;
    box-shadow: none;
}

[data-testid="stSidebar"] .stButton > button > div,
[data-testid="stSidebar"] .stButton > button [data-testid="stMarkdownContainer"] {
    width: 100%;
    display: flex;
    justify-content: flex-start;
}

[data-testid="stSidebar"] .stButton > button p {
    color: inherit !important;
    font-size: 1rem;
    margin: 0;
    width: 100%;
    text-align: left !important;
}

[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,.09);
    color: #fff;
}

[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {
    background: var(--blue);
    color: #fff;
}

/* หัวข้อแอป: โลโก้ + ชื่อ อยู่แถวบนสุด มีเส้นคั่นก่อนเมนู */
.brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 2px 6px 16px;
    margin-bottom: 6px;
    border-bottom: 1px solid rgba(255,255,255,.14);
}

.brand-logo {
    width: 44px; height: 44px;
    border-radius: 12px;
    background: var(--blue);
    display: grid; place-items: center;
    color: #fff; font-size: 1.4rem;
}

.brand-title { color: #fff; font-weight: 700; font-size: 1.12rem; line-height: 1.2; }
.brand-sub   { color: #94a3b8; font-size: .78rem; }

.side-status {
    margin-top: 1.2rem;
    padding: 12px 14px;
    border: 1px solid rgba(255,255,255,.16);
    border-radius: 12px;
    color: #cbd5e1;
    font-size: .8rem;
}

.side-status b {
    color: #fff;
    display: flex; align-items: center; gap: 8px;
    margin-bottom: 2px;
}

.dot { width: 9px; height: 9px; border-radius: 50%; background: #64748b; display: inline-block; }
.dot.on { background: #22c55e; }

/* ---------- การ์ด (st.container(key="card_...")) ---------- */

[class*="st-key-card_"] {
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 1.1rem 1.25rem 1.2rem;
    box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 6px 18px rgba(15,23,42,.04);
}

.sec-title { font-size: 1.12rem; font-weight: 700; color: var(--text); }
.sec-sub   { font-size: .86rem; color: var(--muted); margin: 2px 0 10px; }

/* ---------- หัวหน้า ---------- */

.page-head {
    display: flex; align-items: center; gap: 16px;
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 16px 20px;
    margin-bottom: 14px;
    box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 6px 18px rgba(15,23,42,.04);
}

.page-head .ic {
    width: 56px; height: 56px;
    border-radius: 14px;
    background: var(--blue-soft);
    display: grid; place-items: center;
    font-size: 1.7rem;
    flex: none;
}

.ph-title { font-size: 1.65rem; font-weight: 700; color: var(--text); line-height: 1.25; }
.ph-sub   { color: var(--muted); font-size: .95rem; margin-top: 2px; }

/* ---------- Upload ---------- */

[data-testid="stFileUploaderDropzone"] {
    border: 1.5px dashed #b6c8ea;
    background: #f8fbff;
    border-radius: 12px;
}

/* ---------- ป้ายสถานะ ---------- */

.chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 3px 11px;
    border-radius: 999px;
    font-size: .8rem; font-weight: 600;
    white-space: nowrap;
}

.chip i {
    width: 7px; height: 7px; border-radius: 50%;
    background: currentColor; display: inline-block;
}

.chip-green { background: var(--green-bg); color: var(--green-tx); }
.chip-amber { background: var(--amber-bg); color: var(--amber-tx); }
.chip-red   { background: var(--red-bg);   color: var(--red-tx); }
.chip-gray  { background: #eef2f7;         color: #64748b; }

.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }

/* ---------- KPI 3 ใบ ---------- */

.kpi-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    margin: 4px 0 16px;
}

.kpi {
    display: flex; align-items: center; gap: 14px;
    padding: 16px 18px;
    border-radius: 14px;
    border: 1px solid;
}

.kpi-green { background: var(--green-bg); border-color: var(--green-bd); }
.kpi-amber { background: var(--amber-bg); border-color: var(--amber-bd); }
.kpi-red   { background: var(--red-bg);   border-color: var(--red-bd); }

.kpi-ic {
    width: 44px; height: 44px; border-radius: 50%;
    display: grid; place-items: center;
    color: #fff; font-size: 1.25rem; font-weight: 700;
    flex: none;
}

.kpi-green .kpi-ic { background: var(--green); }
.kpi-amber .kpi-ic { background: #f59e0b; }
.kpi-red   .kpi-ic { background: var(--red); }

.kpi-label { font-size: .9rem; font-weight: 600; color: #334155; }
.kpi-green .kpi-label { color: var(--green-tx); }
.kpi-amber .kpi-label { color: var(--amber-tx); }
.kpi-red   .kpi-label { color: var(--red-tx); }

.kpi-value { font-size: 1.7rem; font-weight: 700; line-height: 1.15; color: var(--text); }
.kpi-pct   { font-size: .85rem; font-weight: 500; color: var(--muted); }

/* ---------- ตาราง ---------- */

.tbl-wrap {
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-top: 6px;
}

table.tbl { width: 100%; border-collapse: collapse; font-size: .9rem; }

.tbl th {
    background: #f5f8fd;
    color: #475569;
    font-weight: 600;
    text-align: left;
    padding: 10px 12px;
    white-space: nowrap;
}

.tbl td {
    padding: 10px 12px;
    border-top: 1px solid #eef2f8;
    color: var(--text);
}

.tbl tbody tr:hover td { background: #fafcff; }

.tbl .r { text-align: right; font-variant-numeric: tabular-nums; }
.tbl .c { text-align: center; }
.tbl th.r { text-align: right; }
.tbl th.c { text-align: center; }
.tbl .neg { color: var(--red); font-weight: 600; }
.tbl .empty { text-align: center; color: var(--muted); padding: 28px; }

/* ---------- แผงสรุปด้านขวา ---------- */

.stat {
    display: flex; align-items: center; gap: 14px;
    padding: 12px 0;
    border-bottom: 1px solid #eef2f8;
}

.stat:last-child { border-bottom: 0; }

.stat-ic {
    width: 42px; height: 42px; border-radius: 50%;
    background: var(--blue-soft);
    display: grid; place-items: center;
    font-size: 1.15rem; flex: none;
}

.stat-label { color: var(--muted); font-size: .84rem; }
.stat-value { font-size: 1.3rem; font-weight: 700; color: var(--text); line-height: 1.25; }

/* ---------- อื่น ๆ ---------- */

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

.small { color: var(--muted); font-size: .88rem; }

.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {
    border-radius: 12px;
    font-weight: 600;
}

/* ---------- หน้า "รายละเอียดออเดอร์": ขั้นตอน / แถบสถานะ / ปุ่ม ---------- */

.step-head { display:flex; align-items:center; gap:10px; margin:0 0 4px; }
.step-head .n {
    width:28px; height:28px; border-radius:50%; flex:none;
    background:linear-gradient(135deg,#2563eb,#1d4ed8); color:#fff;
    display:grid; place-items:center; font-weight:700; font-size:.9rem;
    box-shadow:0 2px 6px rgba(37,99,235,.35);
}
.step-head .t { font-weight:700; font-size:1.08rem; color:var(--text); }
.step-head .h { color:var(--muted); font-size:.84rem; margin-left:2px; }

.status-bar { display:flex; flex-wrap:wrap; gap:8px; margin:2px 0 10px; }
.status-bar .pill {
    background:#fff; border:1px solid var(--border); border-radius:999px;
    padding:5px 12px; font-size:.84rem; color:var(--text);
    box-shadow:0 1px 2px rgba(15,23,42,.04);
}
.status-bar .pill b { color:var(--blue); }

/* ตัวเลือกแบบ radio แนวนอน → ปุ่มแคปซูล */
.st-key-od_source [role="radiogroup"],
.st-key-od_view [role="radiogroup"],
.st-key-od_mode [role="radiogroup"] {
    gap:6px; background:#e9eef7; padding:4px; border-radius:12px; width:fit-content;
}
.st-key-od_source [role="radiogroup"] label,
.st-key-od_view [role="radiogroup"] label,
.st-key-od_mode [role="radiogroup"] label {
    background:transparent; padding:6px 14px; border-radius:9px; margin:0; cursor:pointer;
}
.st-key-od_source [role="radiogroup"] label:has(input:checked),
.st-key-od_view [role="radiogroup"] label:has(input:checked),
.st-key-od_mode [role="radiogroup"] label:has(input:checked) {
    background:#fff; box-shadow:0 1px 4px rgba(15,23,42,.14); font-weight:600;
}
.st-key-od_source [role="radiogroup"] label > div:first-child,
.st-key-od_view [role="radiogroup"] label > div:first-child,
.st-key-od_mode [role="radiogroup"] label > div:first-child { display:none; }

/* ปุ่มหลัก */
.stButton > button[kind="primary"] {
    background:linear-gradient(135deg,#2563eb,#1d4ed8); border:0; color:#fff;
    box-shadow:0 4px 12px rgba(37,99,235,.28); transition:transform .08s, box-shadow .15s;
}
.stButton > button[kind="primary"]:hover { transform:translateY(-1px); box-shadow:0 6px 16px rgba(37,99,235,.36); }
.stButton > button[kind="primary"]:disabled { background:#cbd5e1; box-shadow:none; color:#fff; }
.stButton > button:not([kind="primary"]) { border-radius:12px; }

/* ช่องอัปโหลด */
[data-testid="stFileUploaderDropzone"] {
    border:1.5px dashed #b6c6e6; border-radius:14px; background:#f8faff;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color:var(--blue); background:#f1f6ff; }

/* ตาราง / expander / การแจ้งเตือน */
[data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:12px; overflow:hidden; }
[data-testid="stExpander"] { border:1px solid var(--border) !important; border-radius:12px !important; background:#fff; }
[data-testid="stAlert"] { border-radius:12px; }


/* ---------- หน้าหลัก / ตั้งค่า / แดชบอร์ด ของ "รายละเอียดออเดอร์" ---------- */

.src-card { text-align:center; padding:14px 6px 8px; }
.src-card .src-ic { font-size:2.6rem; line-height:1.2; }
.src-card .src-t  { font-weight:700; font-size:1.15rem; margin-top:4px; }
.src-card .src-d  { color:var(--muted); font-size:.88rem; margin:4px 0 10px; }

.setup-head { display:flex; align-items:center; gap:14px; margin-bottom:6px; }
.setup-head .ic { font-size:2rem; }
.setup-head .t { font-weight:700; font-size:1.2rem; }
.setup-head .d { color:var(--muted); font-size:.88rem; }

.status-bar .pill.tone-green  { background:var(--green-bg);  border-color:var(--green-bd);  color:var(--green-tx); font-weight:600; }
.status-bar .pill.tone-purple { background:#f1ebff; border-color:#d9c9fb; color:#6d28d9; font-weight:600; }
.updated { color:var(--muted); font-size:.82rem; text-align:right; }

.kpi2-row { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin:4px 0 14px; }
@media (max-width: 1000px) { .kpi2-row { grid-template-columns:repeat(2,minmax(0,1fr)); } }

.kpi2 {
    display:flex; align-items:center; gap:14px; padding:16px 18px;
    border-radius:16px; border:1px solid var(--border); background:#fff;
    box-shadow:0 1px 2px rgba(15,23,42,.04), 0 6px 18px rgba(15,23,42,.04);
}
.kpi2 .ic { width:48px; height:48px; border-radius:14px; display:grid; place-items:center; font-size:1.4rem; flex:none; }
.kpi2 .l  { color:var(--muted); font-size:.84rem; }
.kpi2 .v  { font-size:1.7rem; font-weight:800; color:var(--text); line-height:1.2; }
.kpi2 .s  { color:var(--muted); font-size:.8rem; }
.kpi2.tone-blue   { background:linear-gradient(135deg,#f3f8ff,#fff); } .kpi2.tone-blue   .ic { background:#dbeafe; }
.kpi2.tone-green  { background:linear-gradient(135deg,#effaf3,#fff); } .kpi2.tone-green  .ic { background:#d1f2dc; }
.kpi2.tone-amber  { background:linear-gradient(135deg,#fff8ea,#fff); } .kpi2.tone-amber  .ic { background:#fde8bd; }
.kpi2.tone-red    { background:linear-gradient(135deg,#fff1f1,#fff); } .kpi2.tone-red    .ic { background:#fbd0d0; }
.kpi2.tone-purple { background:linear-gradient(135deg,#f6f1ff,#fff); } .kpi2.tone-purple .ic { background:#e6dbfc; }

</style>
"""


def apply_styles():
    st.markdown(CSS, unsafe_allow_html=True)