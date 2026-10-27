"""ฟังก์ชันกลางที่ใช้ร่วมกันหลายไฟล์ (ไม่มี UI)"""

import io

import pandas as pd


def money(x):
    return f"{float(x or 0):,.2f} บาท"


def clean_order_col(df):
    """หาชื่อคอลัมน์เลขที่ออเดอร์"""

    if "เลขที่ออเดอร์" in df.columns:
        return "เลขที่ออเดอร์"

    if "order_number" in df.columns:
        return "order_number"

    return None


def clean_channel_col(df):
    """หาชื่อคอลัมน์ช่องทาง"""

    if "ช่องทางการขาย" in df.columns:
        return "ช่องทางการขาย"

    if "ช่องทางที่ลูกค้าทักมา" in df.columns:
        return "ช่องทางที่ลูกค้าทักมา"

    return None


def read_excel(uploaded, sheet_name=None):
    """อ่านไฟล์ Excel จาก st.file_uploader"""

    if uploaded is None:
        return None

    data = uploaded.getvalue()

    if sheet_name is not None and sheet_name != "":
        return pd.read_excel(
            io.BytesIO(data),
            sheet_name=sheet_name
        )

    return pd.read_excel(io.BytesIO(data))
