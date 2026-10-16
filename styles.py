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

[data-testid="stSidebar"] .stButton > button {
    justify-content: flex-start;
    text-align: left;
    border: 0;
    border-radius: 12px;
    padding: .7rem .9rem;
    background: transparent;
    color: #cbd5e1;
    font-weight: 500;
    box-shadow: none;
}

[data-testid="stSidebar"] .stButton > button p {
    color: inherit !important;
    font-size: 1rem;
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

.brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 4px 20px;
}

.brand-logo {
    width: 44px; height: 44px;
    border-radius: 12px;
    background: var(--blue);
    display: grid; place-items: center;
    color: #fff; font-size: 1.4rem;
}

.brand-title { color: #fff; font-weight: 700; font-size: 1.02rem; line-height: 1.2; }
.brand-sub   { color: #94a3b8; font-size: .78rem; }

.side-status {
    margin-top: 2.2rem;
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

</style>
"""


def apply_styles():
    st.markdown(CSS, unsafe_allow_html=True)
