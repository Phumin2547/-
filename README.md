# Order Reconciliation Web

เว็บสำหรับเปลี่ยน workflow จาก `ORDER_ver2.ipynb` ให้ user ใช้งานผ่านหน้าเว็บ

## ฟังก์ชัน
- Upload Excel: Shipnity / Category / ใบรายงาน
- สรุปจำนวนออเดอร์และยอดขาย
- Channel: Online Marketing / Call Center
- เปรียบเทียบ Shipnity กับใบรายงาน
- แยกออเดอร์เฉพาะแต่ละแหล่ง
- แยกยอดขายตรงกัน / ไม่ตรงกัน
- ค้นหาเลขที่ออเดอร์
- Export ตารางที่กำลังดูเป็น CSV
- ดูข้อมูลต้นฉบับ

## วิธีรัน

```bash
pip install -r requirements.txt
streamlit run app.py
```

จากนั้นเปิด URL ที่ Streamlit แสดงใน Terminal

> หมายเหตุ: logic การจัด Channel และการเปรียบเทียบออเดอร์ถูกถอดจาก `ORDER_ver2.ipynb` โดยตรงและปรับเฉพาะส่วน input/output ให้เหมาะกับเว็บ
