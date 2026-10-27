"""กฎแบ่ง Channel (Call Center / Online Marketing) ของหน้าตรวจสอบออเดอร์"""

import re

STAFF_PATTERN = r"\b(?:VP|OB)\d+\b"


def classify_channel(df, channel_col, employee_col=None):

    out = df.copy()

    def classify(row):

        channel = str(
            row.get(channel_col, "")
        ).strip().lower()

        employee = (
            str(row.get(employee_col, "")).strip().upper()
            if employee_col
            else ""
        )

        note = str(
            row.get("หมายเหตุ", "")
        ).strip().upper()

        # ---- OTHER ----

        if "other" in channel:

            if "phone" in channel:
                return "Call Center"

            if re.search(STAFF_PATTERN, employee):
                return "Call Center"

            if re.search(STAFF_PATTERN, note):
                return "Call Center"

            return "Online Marketing"

        # ---- PHONE ----

        if "phone" in channel:
            return "Call Center"

        # ---- Employee VP / OB ----

        if re.search(STAFF_PATTERN, employee):
            return "Call Center"

        # ---- Note VP / OB ----

        if re.search(STAFF_PATTERN, note):
            return "Call Center"

        # ---- Default ----

        return "Online Marketing"

    out["Channel_Category"] = out.apply(classify, axis=1)

    return out
