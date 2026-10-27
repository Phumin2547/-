# Order Reconciliation

รัน: `pip install -r requirements.txt` แล้ว `streamlit run app.py`

## โครงสร้าง
- `app.py` — จุดเริ่มต้น + เมนู sidebar
- `frontend/` — ส่วนหน้าจอ (Streamlit / CSS / กราฟ)
  - `styles.py`, `ui.py`, `shipnity_widgets.py`
  - `views/` — แต่ละหน้า: order_cn_page, order_page, cn_page, work_files_page, order_detail_page, guide_page
- `backend/` — ตรรกะและการดึงข้อมูล (ไม่ import streamlit/plotly)
  - `shipnity_api.py` (GraphQL ออเดอร์ + **ใส่ Cookie ที่นี่**), `shipnity_promo.py` (รายงานโปรโมชั่น)
  - `shipnity_request.json`, `shipnity_request_promo.json` (request ที่คัดลอกจากเบราว์เซอร์)
  - `work_files_logic.py`, `order_detail_logic.py`, `order_logic.py`, `cn_logic.py`, `channel.py`, `utils.py`

⚠️ อย่าอัปโหลด `backend/shipnity_api.py` ที่มี Cookie ขึ้น GitHub
