"""จุดเริ่มต้นของแอป: รัน  streamlit run app.py"""

import streamlit as st

st.set_page_config(
    page_title="Order Reconciliation Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

from order_cn_page import render_order_cn_page  # noqa: E402
from styles import apply_styles  # noqa: E402
from order_detail_page import render_order_detail_page  # noqa: E402
from ui import sidebar_brand, sidebar_status  # noqa: E402
from work_files_page import render_work_files_page  # noqa: E402

apply_styles()

# เมนูใน sidebar (เพิ่มฟีเจอร์ใหม่: เพิ่มชื่อที่นี่ + ใส่ if ด้านล่าง)
FEATURES = [
    "📋 ตรวจสอบ Order & CN",
    "🗂️ ไฟล์งาน",
    "🔎 รายละเอียดออเดอร์",
]

if st.session_state.get("feature") not in FEATURES:
    st.session_state.feature = FEATURES[0]

with st.sidebar:

    sidebar_brand()

    for name in FEATURES:

        is_active = st.session_state.feature == name

        if st.button(
            name,
            key=f"nav_{name}",
            type="primary" if is_active else "secondary",
            use_container_width=True
        ):
            st.session_state.feature = name
            st.rerun()

    sidebar_status(st.session_state.get("last_run"))

if st.session_state.feature == FEATURES[0]:
    render_order_cn_page()

if st.session_state.feature == FEATURES[1]:
    render_work_files_page()

if st.session_state.feature == FEATURES[2]:
    render_order_detail_page()