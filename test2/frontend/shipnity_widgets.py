"""ชิ้นส่วนหน้าจอที่ใช้ร่วมกันของการดึงข้อมูล Shipnity (ตัวเลือกช่วงเวลา, secrets)"""

import pandas as pd
import streamlit as st

from backend import shipnity_api as sn


def secrets():
    """ค่าใต้ [shipnity] ใน .streamlit/secrets.toml (ไม่มีไฟล์ = ว่าง)"""

    try:
        return dict(st.secrets.get("shipnity", {}))
    except Exception:  # noqa: BLE001
        return {}


def today_th():
    return pd.Timestamp.now(tz="Asia/Bangkok").date()


def year_label(y):
    return f"{y} (พ.ศ. {y + 543})"


def pick_period(today, prefix="wf"):
    """ช่องเลือกช่วงเวลา → คืน (วันเริ่ม, วันสิ้นสุด) หรือ None ถ้าช่วงที่เลือกใช้ไม่ได้"""

    mode = st.radio(
        "ดึงข้อมูลแบบ",
        sn.MODES,
        horizontal=True,
        key=f"{prefix}_mode"
    )

    years = list(range(today.year, today.year - 6, -1))

    kw = {}

    if mode == sn.MODE_SINGLE:

        kw["single"] = st.date_input(
            "วันที่", value=today, max_value=today,
            format="DD/MM/YYYY", key=f"{prefix}_single"
        )

    elif mode == sn.MODE_RANGE:

        picked = st.date_input(
            "ช่วงวันที่สร้างออเดอร์", value=(today, today), max_value=today,
            format="DD/MM/YYYY", key=f"{prefix}_range"
        )

        picked = list(picked) if isinstance(picked, (list, tuple)) else [picked]

        kw["start"] = picked[0] if picked else today
        kw["end"] = picked[-1] if picked else today

    elif mode == sn.MODE_LAST:

        a, b, _ = st.columns([1, 1, 3])

        kw["n"] = a.number_input(
            "ย้อนหลัง", min_value=1, max_value=999, value=7, step=1, key=f"{prefix}_last_n"
        )

        kw["unit"] = b.selectbox("หน่วย", sn.LAST_UNITS, key=f"{prefix}_last_unit")

    elif mode == sn.MODE_MONTH:

        a, b, _ = st.columns([1, 1, 3])

        kw["year"] = a.selectbox("ปี", years, format_func=year_label, key=f"{prefix}_m_year")

        kw["month"] = b.selectbox(
            "เดือน", list(range(1, 13)), index=today.month - 1,
            format_func=lambda m: sn.THAI_MONTHS[m - 1], key=f"{prefix}_m_month"
        )

    else:

        a, _ = st.columns([1, 4])

        kw["year"] = a.selectbox("ปี", years, format_func=year_label, key=f"{prefix}_y_year")

    try:
        return sn.resolve_range(mode, today, **kw)
    except ValueError as e:
        st.warning(str(e))
        return None
