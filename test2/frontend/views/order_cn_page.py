"""หน้า "ตรวจสอบ Order & CN" — ฟีเจอร์เดียวที่รวมการตรวจสอบ 2 แบบ

เลือกแท็บเพื่อตรวจสอบ:
    📦 ตรวจสอบออเดอร์   (Shipnity vs ใบรายงาน, เทียบยอด Express ได้)
    ↩️ ตรวจสอบ CN       (Shipnity vs Express: ใบลดหนี้ / รับคืนสินค้า)

ใช้ st.tabs เพื่อให้ไฟล์ที่อัปโหลดและผลลัพธ์ของแต่ละแบบยังอยู่ครบ
แม้สลับไปมาระหว่างแท็บ
"""

import streamlit as st

from frontend.views.cn_page import render_cn_page
from frontend.views.order_page import render_order_page
from frontend.ui import page_header


def render_order_cn_page():

    page_header(
        "📋",
        "ตรวจสอบ Order & CN",
        "ตรวจสอบออเดอร์/ยอดขาย และรายการลดหนี้ / รับคืนสินค้า (CN) "
        "ระหว่าง Shipnity กับใบรายงานและ Express — เลือกแท็บด้านล่างว่าจะตรวจสอบอะไร"
    )

    tab_order, tab_cn = st.tabs(
        [
            "📦 ตรวจสอบออเดอร์",
            "↩️ ตรวจสอบ CN",
        ]
    )

    with tab_order:
        render_order_page()

    with tab_cn:
        render_cn_page()
