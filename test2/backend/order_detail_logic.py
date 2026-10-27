"""ตรรกะหน้า "รายละเอียดออเดอร์": อ่าน CSV Express, อ่านรายงานโปรโมชั่น Shipnity (แบบบล็อก),
เทียบใบกำกับ/รหัสสินค้า, สร้างตารางรายออเดอร์, ส่งออก Excel (ไม่มี UI)"""

import io
import re

import pandas as pd


INV_CHANNEL_COL, INV_CUSTOMER_COL, INV_GROUP_COL, INV_SALES_COL, INV_ORDER_COL = 0, 1, 4, 9, 10


INV_NO_COL, INV_CODE_COL, INV_NAME_COL, INV_QTY_COL, INV_NET_COL = 14, 3, 4, 5, 7


INV_SHIPPING_CODE = "4230"   # ค่าจัดส่ง: CSV เป็นบรรทัดสินค้า, Shipnity เป็นคอลัมน์ค่าส่ง จึงไม่เทียบจำนวน


INV_NO_RE = r"^[A-Z]{2}\d+$"


def _csv_lines(data):
    """CSV รายงาน Express → DataFrame คอลัมน์แรก = ข้อความ 1 บรรทัด
    (อ่านเป็นบรรทัดตรง ๆ กันคอมมาในตัวเลข เช่น 1,541.00 ทำให้บรรทัดขาด)"""

    for enc in ["utf-8-sig", "cp874", "tis-620"]:

        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("cp874", errors="replace")

    lines = [
        ln.strip('"') if ln.startswith('"') and ln.endswith('"') else ln
        for ln in text.splitlines()
    ]

    return pd.DataFrame({"line": lines[1:]})   # ข้ามบรรทัดหัวเหมือน read_csv


def _inv_norm_code(x):
    """ทำรหัสสินค้าให้เทียบกันได้ ('W TEST HAP1' ↔ 'W_TEST_HAP1', ตัดเลข 0 หน้ารหัสตัวเลขล้วน)"""

    x = re.sub(r"[\s\xa0_]+", "_", str(x).strip()).upper()

    return x.lstrip("0") if x.isdigit() else x


def _parse_invoice_report(df, channel_name):
    """1 บรรทัดหัวบิล = 1 ใบกำกับ, ยอดขาย = “รวมทั้งสิ้น” (ทศนิยมตัวสุดท้ายก่อนวันครบกำหนด)"""

    pat = re.compile(
        r"^\s*(\d{2}/\d{2}/\d{2})\s+([A-Z]{2}\d+)\s+(.*?)"
        r"\s+(\d{2}/\d{2}/\d{2})\s+([A-Z]{2}\d+)\s+([YN])\s*$"
    )

    rows = []

    for line in df.iloc[:, 0].dropna().astype(str):

        m = pat.match(line.strip())

        if not m:
            continue

        date, inv, middle, _due, so, _paid = m.groups()

        amounts = re.findall(r"(?<![A-Z])\d[\d,]*\.\d{2}", middle)

        if not amounts:
            continue

        rows.append({
            "ประเภทช่องทาง": channel_name, "วันที่": date,
            "เลขที่ใบกำกับสินค้า": inv, "ใบสั่งขาย": so,
            "ยอดขาย": float(amounts[-1].replace(",", "")),
            "รายละเอียด": middle.strip(),      # ข้อความระหว่างเลขใบกำกับกับยอด (มักมีรหัสลูกค้า/ชื่อ)
        })

    return pd.DataFrame(
        rows,
        columns=["ประเภทช่องทาง", "วันที่", "เลขที่ใบกำกับสินค้า", "ใบสั่งขาย", "ยอดขาย", "รายละเอียด"]
    )


def _parse_csv_items(df, channel_name):
    """รายการสินค้าในแต่ละใบกำกับของ CSV"""

    inv_pat = re.compile(r"^\s*\d{2}/\d{2}/\d{2}\s+([A-Z]{2}\d+)\s")
    item_pat = re.compile(r"^\s+(\d+)\s+(\S+)\s+(.*?)\s+[A-Z]{2}\d+-\s*(\d+)\s*$")

    rows, cur = [], None

    for raw in df.iloc[:, 0].dropna().astype(str):

        line = raw.replace("\xa0", " ").rstrip()

        m = inv_pat.match(line)

        if m:
            cur = m.group(1)
            continue

        m = item_pat.match(line)

        if not m or cur is None:
            continue

        _no, code, middle, _so_line = m.groups()

        toks = middle.split()

        nums = []

        while toks and re.fullmatch(r"-?\d[\d,]*\.\d{2}", toks[-1]):
            nums.insert(0, float(toks.pop().replace(",", "")))

        if not toks or not re.match(r"^\d+\D", toks[-1]):
            continue

        qty = int(re.match(r"^\d+", toks.pop()).group())

        rows.append({
            "เลขที่ใบกำกับ": cur, "ประเภทช่องทาง": channel_name,
            "รหัสสินค้า": _inv_norm_code(code), "ชื่อรายการ (CSV)": " ".join(toks),
            "จำนวน CSV": qty,
            "จำนวนเงิน CSV": nums[-1] if nums else 0.0,
        })

    return pd.DataFrame(
        rows,
        columns=["เลขที่ใบกำกับ", "ประเภทช่องทาง", "รหัสสินค้า",
                 "ชื่อรายการ (CSV)", "จำนวน CSV", "จำนวนเงิน CSV"]
    )


def _carrier_of(group):
    """ชื่อกลุ่มของบล็อก Shipnity → (ขนส่ง, วิธีชำระ)
    เช่น "Kerry COD /SK" → (Kerry, COD) · "DHL โอนเงิน/SE" → (DHL, โอนเงิน)
    กลุ่มมาร์เก็ตเพลส (Lazada/TikTok/Shopee) ไม่มีขนส่งในชื่อ จึงแยกเป็นกลุ่มของตัวเอง"""

    g = str(group).strip().lower()

    for key, name in [
        ("kerry", "Kerry"), ("dhl", "DHL"), ("speed", "Speed"),
        ("lazada", "Lazada"), ("tiktok", "TikTok"),
        ("j&t", "J&T"), ("spx", "SPX"), ("flash", "Flash"),
        ("shoppee", "Shopee"), ("shopee", "Shopee"),
    ]:
        if key in g:
            carrier = name
            break
    else:
        carrier = "อื่นๆ (ลูกค้าองค์กร)"

    pay = "COD" if "cod" in g else "โอนเงิน" if "โอน" in g else "-"

    return carrier, pay


def _invoice_compare(promo_data, online_data, call_data):
    """คืน dict ผลเทียบทั้งหมด"""

    df_online = _csv_lines(online_data)
    df_call = _csv_lines(call_data)
    df_promo = pd.read_excel(io.BytesIO(promo_data), header=None)
    df_promo = df_promo.reindex(columns=range(max(15, df_promo.shape[1])))   # คอลัมน์ท้ายที่ว่างทั้งหมดถูกตัดตอนอ่าน

    on_orders = _parse_invoice_report(df_online, "Online")
    cc_orders = _parse_invoice_report(df_call, "Call Center")

    # ---------- Shipnity: แยกบล็อกตามหัวตาราง ----------

    header_rows = [
        r for r in range(len(df_promo))
        if str(df_promo.iat[r, INV_CHANNEL_COL]).strip() == "ช่องทางการเปิดบิล"
    ]

    if not header_rows:
        raise ValueError("ไม่พบหัวตาราง “ช่องทางการเปิดบิล” ในไฟล์ Shipnity โปรโมชั่น")

    bounds = header_rows + [len(df_promo)]

    records = []

    for block_no, (start, end) in enumerate(zip(bounds, bounds[1:]), 1):

        block = df_promo.iloc[start + 1:end]

        if block.empty:
            continue

        channel = str(block.iat[0, INV_CHANNEL_COL]).strip()

        group = df_promo.iat[start - 1, INV_GROUP_COL] if start > 0 else None

        for _, row in block.iterrows():

            order_no = row[INV_ORDER_COL]

            if pd.isna(order_no) or str(order_no).strip() == "":
                continue

            records.append({
                "บล็อก": block_no,
                "กลุ่ม": str(group).strip(),
                "ช่องทางการเปิดบิล": channel,
                "เลขที่ออเดอร์": str(order_no).strip(),
                "ยอดขาย": pd.to_numeric(row[INV_SALES_COL], errors="coerce"),
            })

    ship_orders = pd.DataFrame(
        records,
        columns=["บล็อก", "กลุ่ม", "ช่องทางการเปิดบิล", "เลขที่ออเดอร์", "ยอดขาย"]
    ).drop_duplicates(subset=["เลขที่ออเดอร์"])

    # ---------- 1) ตารางเปรียบเทียบรวมตามช่องทาง ----------

    def ship_summary(channel):

        d = ship_orders[ship_orders["ช่องทางการเปิดบิล"] == channel]

        return d["บล็อก"].nunique(), d["เลขที่ออเดอร์"].nunique(), d["ยอดขาย"].sum()

    on_bill, on_ord, on_sales = ship_summary("Online/SK")
    cc_bill, cc_ord, cc_sales = ship_summary("Callcenter/SE")

    csv_on_n, csv_on_s = on_orders["เลขที่ใบกำกับสินค้า"].nunique(), on_orders["ยอดขาย"].sum()
    csv_cc_n, csv_cc_s = cc_orders["เลขที่ใบกำกับสินค้า"].nunique(), cc_orders["ยอดขาย"].sum()

    def srow(name, cn, cs, sb, so, ss):
        return {
            "ประเภทช่องทาง": name, "จำนวนบิล CSV": cn, "จำนวนบิล Shipnity": sb,
            "ผลต่างจำนวนบิล": sb - cn, "จำนวนออเดอร์ Shipnity": so,
            "ยอดขาย CSV": cs, "ยอดขาย Shipnity": ss,
            "ผลต่างยอดขาย": round(ss - cs, 2) + 0.0,
        }

    comparison = pd.DataFrame([
        srow("Online", csv_on_n, csv_on_s, on_bill, on_ord, on_sales),
        srow("Call Center", csv_cc_n, csv_cc_s, cc_bill, cc_ord, cc_sales),
        srow("รวมทั้งหมด", csv_on_n + csv_cc_n, csv_on_s + csv_cc_s,
             on_bill + cc_bill, on_ord + cc_ord, on_sales + cc_sales),
    ])

    # ---------- 2) ขนส่ง / วิธีชำระ ของแต่ละบล็อก ----------

    carrier_blocks = (
        ship_orders.groupby(["บล็อก", "ช่องทางการเปิดบิล", "กลุ่ม"], sort=True)
        .agg(ออเดอร์=("เลขที่ออเดอร์", "nunique"), ยอด_Shipnity=("ยอดขาย", "sum"))
        .reset_index()
    )

    carrier_blocks[["ขนส่ง", "ชำระ"]] = [_carrier_of(g) for g in carrier_blocks["กลุ่ม"]]

    csv_all = pd.concat([on_orders, cc_orders], ignore_index=True)

    # ---------- 3) ตรวจเลขที่ใบกำกับ IK / WG / IE ----------

    df_csv_items = pd.concat(
        [_parse_csv_items(df_online, "Online"), _parse_csv_items(df_call, "Call Center")],
        ignore_index=True
    )

    ps = df_promo.copy()

    is_header = ps[0].astype(str).str.strip().eq("ช่องทางการเปิดบิล")

    ps["_blk"] = is_header.cumsum()

    ps = ps[(ps["_blk"] > 0) & ~is_header].copy()

    inv_ok = ps[INV_NO_COL].astype(str).str.strip().str.match(INV_NO_RE)

    ps["_inv"] = (
        ps[INV_NO_COL].where(inv_ok)
        .groupby(ps["_blk"]).transform(lambda x: x.ffill().bfill())
    )

    sp = ps[ps[INV_CODE_COL].notna() & ps["_inv"].notna()]

    df_ship_items = pd.DataFrame({
        "เลขที่ใบกำกับ": sp["_inv"].astype(str).str.strip(),
        "รหัสสินค้า": sp[INV_CODE_COL].map(_inv_norm_code),
        "ชื่อรายการ (Shipnity)": sp[INV_NAME_COL].astype(str).str.strip(),
        "จำนวน Shipnity": pd.to_numeric(sp[INV_QTY_COL], errors="coerce"),
        "มูลค่าสุทธิ Shipnity": pd.to_numeric(sp[INV_NET_COL], errors="coerce"),
    })

    ord_rows = df_promo[
        df_promo[INV_ORDER_COL].notna()
        & df_promo[INV_NO_COL].notna()
        & df_promo[INV_NO_COL].astype(str).str.match(INV_NO_RE)
    ]

    ship_inv = (
        ord_rows.assign(
            inv=ord_rows[INV_NO_COL].astype(str).str.strip(),
            s=pd.to_numeric(ord_rows[INV_SALES_COL], errors="coerce")
        )
        .groupby("inv")
        .agg(ออเดอร์=(INV_ORDER_COL, "nunique"), ยอด_Shipnity=("s", "sum"))
        .reset_index()
        .rename(columns={"inv": "เลขที่ใบกำกับ"})
    )

    csv_inv = csv_all[["ประเภทช่องทาง", "เลขที่ใบกำกับสินค้า", "ยอดขาย"]].rename(
        columns={"เลขที่ใบกำกับสินค้า": "เลขที่ใบกำกับ", "ยอดขาย": "ยอด_CSV"}
    )

    inv_check = csv_inv.merge(ship_inv, on="เลขที่ใบกำกับ", how="outer", indicator=True)

    inv_check["ผลต่าง"] = (
        inv_check["ยอด_Shipnity"].fillna(0) - inv_check["ยอด_CSV"].fillna(0)
    ).round(2) + 0.0

    inv_check["สถานะ"] = inv_check.apply(
        lambda r: "ไม่มีใน Shipnity" if r["_merge"] == "left_only"
        else "ไม่มีใน CSV" if r["_merge"] == "right_only"
        else "ตรงกัน" if abs(r["ผลต่าง"]) < 0.005 else "ยอดไม่ตรง",
        axis=1
    )

    inv_check = inv_check.drop(columns="_merge").sort_values("เลขที่ใบกำกับ").reset_index(drop=True)

    # ขนส่ง/ชำระ ของแต่ละใบกำกับ (บล็อกเดียวกับที่มีเลขใบกำกับนั้น)
    blk_inv = ps.dropna(subset=["_inv"]).groupby("_blk")["_inv"].first().astype(str).str.strip()

    inv_carrier = carrier_blocks.copy()

    inv_carrier["เลขที่ใบกำกับ"] = inv_carrier["บล็อก"].map(blk_inv)

    inv_carrier = (
        inv_carrier.dropna(subset=["เลขที่ใบกำกับ"])
        .drop_duplicates("เลขที่ใบกำกับ")[["เลขที่ใบกำกับ", "กลุ่ม", "ขนส่ง", "ชำระ"]]
    )

    inv_carrier["เลขที่ใบกำกับ"] = inv_carrier["เลขที่ใบกำกับ"].astype(str)
    inv_check["เลขที่ใบกำกับ"] = inv_check["เลขที่ใบกำกับ"].astype(str)

    inv_check = inv_check.merge(inv_carrier, on="เลขที่ใบกำกับ", how="left")

    # ---------- 4) เทียบรายการสินค้าตามรหัส (ไม่รวมค่าจัดส่ง) ----------

    key = ["เลขที่ใบกำกับ", "รหัสสินค้า"]

    c = (
        df_csv_items[df_csv_items["รหัสสินค้า"] != INV_SHIPPING_CODE]
        .groupby(key)
        .agg(name_csv=("ชื่อรายการ (CSV)", "first"), qty_csv=("จำนวน CSV", "sum"),
             amt_csv=("จำนวนเงิน CSV", "sum"))
        .reset_index()
    )

    s = (
        df_ship_items[df_ship_items["รหัสสินค้า"] != INV_SHIPPING_CODE]
        .groupby(key)
        .agg(name_ship=("ชื่อรายการ (Shipnity)", "first"), qty_ship=("จำนวน Shipnity", "sum"),
             amt_ship=("มูลค่าสุทธิ Shipnity", "sum"))
        .reset_index()
    )

    items = c.merge(s, on=key, how="outer")

    items[["qty_csv", "qty_ship"]] = items[["qty_csv", "qty_ship"]].fillna(0)

    items["name"] = items["name_ship"].fillna(items["name_csv"])

    items["diff"] = items["qty_ship"] - items["qty_csv"]

    items["status"] = items["diff"].apply(
        lambda d: "ตรงกัน" if d == 0 else "Shipnity มากกว่า" if d > 0 else "CSV มากกว่า"
    )

    items = items.rename(columns={
        "name": "ชื่อรายการ", "qty_csv": "จำนวน CSV", "qty_ship": "จำนวน Shipnity",
        "diff": "ผลต่างจำนวน", "amt_csv": "เงิน CSV", "amt_ship": "เงิน Shipnity",
        "status": "สถานะ",
    })

    items = items[key + ["ชื่อรายการ", "จำนวน CSV", "จำนวน Shipnity", "ผลต่างจำนวน",
                         "เงิน CSV", "เงิน Shipnity", "สถานะ"]]

    return {
        "comparison": comparison,
        "inv_check": inv_check,
        "items": items,
        "carrier_blocks": carrier_blocks,
        "ship_blocks": len(header_rows),
        "ship_orders": len(ship_orders),
        "csv_bills": (len(on_orders), len(cc_orders)),
    }


def _build_order_detail(promo_data):
    """แปลงรายงาน Shipnity แบบบล็อกเป็นตารางรายบรรทัดสินค้า (lines) และรายออเดอร์ (orders)"""

    df = pd.read_excel(io.BytesIO(promo_data), header=None)
    df = df.reindex(columns=range(max(15, df.shape[1])))

    required_max_col = max(INV_CHANNEL_COL, INV_GROUP_COL, INV_SALES_COL, INV_ORDER_COL, 14)

    if df.shape[1] <= required_max_col:
        raise ValueError(
            f"ไฟล์ Shipnity มี {df.shape[1]} คอลัมน์ แต่ต้องมีอย่างน้อย {required_max_col + 1} คอลัมน์"
        )

    is_header = df[0].astype(str).str.strip().eq("ช่องทางการเปิดบิล")
    block_ids = is_header.cumsum()
    lines = []

    for block_no in range(1, int(block_ids.max()) + 1):

        header_idx = df.index[(block_ids == block_no) & is_header]

        if len(header_idx) == 0:
            continue

        hdr_idx = header_idx[0]
        group_name = df.iat[hdr_idx - 1, INV_GROUP_COL] if hdr_idx > 0 else ""
        block = df[(block_ids == block_no) & ~is_header].copy()

        if block.empty:
            continue

        channel = str(block.iloc[0, INV_CHANNEL_COL]).strip()
        inv_vals = block.iloc[:, INV_NO_COL].astype(str).str.strip()
        inv_vals = inv_vals[inv_vals.str.match(INV_NO_RE, na=False)]
        invoice = inv_vals.iloc[0] if len(inv_vals) else None

        # แถวที่มีรหัสสินค้า ผูกกับเลขออเดอร์ล่าสุดในบล็อก
        current_order, current_head = None, None

        for _, row in block.iterrows():

            order_value = row.iloc[INV_ORDER_COL]

            if pd.notna(order_value) and str(order_value).strip():
                current_order = str(order_value).strip()
                current_head = row

            code_value = row.iloc[INV_CODE_COL]

            if current_order is None or pd.isna(code_value) or not str(code_value).strip():
                continue

            head = current_head

            lines.append({
                "เลขที่ออเดอร์": current_order,
                "บล็อก": block_no,
                "ช่องทาง": channel,
                "กลุ่ม": "" if pd.isna(group_name) else str(group_name).strip(),
                "เลขที่ใบกำกับ": invoice,
                "ใบสั่งขาย": head.iloc[13],
                "ขนส่ง": head.iloc[12],
                "ค่าส่ง": pd.to_numeric(head.iloc[8], errors="coerce"),
                "ส่วนลด": pd.to_numeric(head.iloc[11], errors="coerce"),
                "ยอดขาย": pd.to_numeric(head.iloc[INV_SALES_COL], errors="coerce"),
                "รหัสสินค้า": _inv_norm_code(code_value),
                "ชื่อรายการ": "" if pd.isna(row.iloc[INV_NAME_COL]) else str(row.iloc[INV_NAME_COL]).strip(),
                "จำนวน": pd.to_numeric(row.iloc[INV_QTY_COL], errors="coerce"),
                "ราคา": pd.to_numeric(row.iloc[6], errors="coerce"),
                "มูลค่าสุทธิ": pd.to_numeric(row.iloc[7], errors="coerce"),
            })

    lines_df = pd.DataFrame(lines)

    if lines_df.empty:
        return lines_df, pd.DataFrame()

    order_rows = []

    for order_no, group in lines_df.groupby("เลขที่ออเดอร์", sort=False, dropna=False):

        first = group.iloc[0]

        items_text = group.apply(
            lambda r: f"{r['รหัสสินค้า']} {r['ชื่อรายการ']}"
                      + (f" ×{r['จำนวน']:g}" if pd.notna(r["จำนวน"]) else ""),
            axis=1
        ).tolist()

        order_rows.append({
            "เลขที่ออเดอร์": order_no,
            "ช่องทาง": first["ช่องทาง"],
            "เลขที่ใบกำกับ": first["เลขที่ใบกำกับ"],
            "กลุ่ม": first["กลุ่ม"],
            "ขนส่ง": first["ขนส่ง"],
            "ยอดขาย": group["ยอดขาย"].dropna().iloc[0] if group["ยอดขาย"].notna().any() else 0,
            "ค่าส่ง": first["ค่าส่ง"],
            "ส่วนลด": first["ส่วนลด"],
            "จำนวนรายการ": len(group),
            "จำนวนชิ้นรวม": group["จำนวน"].sum(),
            "รายการสินค้า": " | ".join(items_text),
        })

    return lines_df, pd.DataFrame(order_rows)


def _excel_bytes(promo_data, online_data, call_data):
    """ไฟล์ Excel สรุปผลทั้งหมด (สร้างครั้งเดียว เก็บแคช)"""

    res = _invoice_compare(promo_data, online_data, call_data)
    lines_df, orders_df = _build_order_detail(promo_data)

    out = io.BytesIO()

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        res["comparison"].to_excel(writer, sheet_name="เทียบยอด CSV Shipnity", index=False)
        res["inv_check"].to_excel(writer, sheet_name="ตรวจใบกำกับ", index=False)
        res["items"].to_excel(writer, sheet_name="เทียบรายการสินค้า", index=False)
        orders_df.to_excel(writer, sheet_name="รายออเดอร์", index=False)
        lines_df.to_excel(writer, sheet_name="รายการสินค้าทั้งหมด", index=False)

    return out.getvalue()
