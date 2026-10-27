"""ตรรกะของหน้า "ไฟล์งาน": อ่าน/เตรียมข้อมูลออเดอร์ Shipnity, จับจังหวัด, คำนวณ Insight (ไม่มี UI)"""

import io
import re

import pandas as pd

from backend.channel import classify_channel


COL_ORDER = "เลขที่ออเดอร์"


COL_SALES = "ยอดขาย"


COL_CH = "ช่องทางที่ลูกค้าทักมา"


COL_SHIP = "ขนส่ง"


COL_BANK = "ธนาคารที่รับเงิน"


COL_NOTE = "หมายเหตุ"


COL_CUST = "รหัสลูกค้า (ลูกค้า)"


COL_NAME = "ชื่อ (ลูกค้า)"


COL_PHONE = "เบอร์โทร (ลูกค้า)"


COL_DISC = "ส่วนลดจาก Marketplace"


COL_CREATED = "วันที่สร้าง"


COL_ADDR = "ที่อยู่ (ลูกค้า)"


COL_CANCEL = "ยกเลิกออเดอร์แล้ว"


REQUIRED = [COL_ORDER, COL_SALES, COL_CH, COL_SHIP]


MARKET = ["Shopee", "TikTok", "Lazada"]


PAID_BANKS = ["กสิกร", "กรุงเทพ", "กรุงไทย", "บัตรเครดิต", "Paysbuy"]


NOTE_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*,\s*([^,]*),\s*([^,]*)")


PO_RE = re.compile(r"PO\.[A-Za-z0-9]+")


PROVINCES = (
    "กระบี่ กรุงเทพมหานคร กาญจนบุรี กาฬสินธุ์ กำแพงเพชร ขอนแก่น จันทบุรี "
    "ฉะเชิงเทรา ชลบุรี ชัยนาท ชัยภูมิ ชุมพร เชียงราย เชียงใหม่ ตรัง ตราด ตาก "
    "นครนายก นครปฐม นครพนม นครราชสีมา นครศรีธรรมราช นครสวรรค์ นนทบุรี "
    "นราธิวาส น่าน บึงกาฬ บุรีรัมย์ ปทุมธานี ประจวบคีรีขันธ์ ปราจีนบุรี "
    "ปัตตานี พระนครศรีอยุธยา พะเยา พังงา พัทลุง พิจิตร พิษณุโลก เพชรบุรี "
    "เพชรบูรณ์ แพร่ ภูเก็ต มหาสารคาม มุกดาหาร แม่ฮ่องสอน ยโสธร ยะลา ร้อยเอ็ด "
    "ระนอง ระยอง ราชบุรี ลพบุรี ลำปาง ลำพูน เลย ศรีสะเกษ สกลนคร สงขลา สตูล "
    "สมุทรปราการ สมุทรสงคราม สมุทรสาคร สระแก้ว สระบุรี สิงห์บุรี สุโขทัย "
    "สุพรรณบุรี สุราษฎร์ธานี สุรินทร์ หนองคาย หนองบัวลำภู อ่างทอง อำนาจเจริญ "
    "อุดรธานี อุตรดิตถ์ อุทัยธานี อุบลราชธานี"
).split()


PROV_BY_LEN = sorted(PROVINCES, key=len, reverse=True)


PROV_TAG_RE = re.compile(r"(?:จังหวัด|จ\.|จ\s)\s*([ก-๙]+)")


BKK_RE = re.compile(r"กรุงเทพ|กทม|bangkok|แขวง", re.I)


def _norm_channel(s):

    t = str(s).strip().lower()

    for key, name in [
        ("fb", "Facebook"),
        ("facebook", "Facebook"),
        ("shopee", "Shopee"),
        ("tiktok", "TikTok"),
        ("lazada", "Lazada"),
        ("line", "Line"),
        ("phone", "โทรศัพท์"),
    ]:
        if t.startswith(key):
            return name

    return "อื่นๆ"


def _page_name(s):

    s = str(s)

    return s.split(":", 1)[1].strip() if ":" in s else ""


def _province(addr):
    """ดึงชื่อจังหวัดจากที่อยู่ (ไม่พบ = "ไม่ระบุที่อยู่")"""

    if pd.isna(addr):
        return "ไม่ระบุที่อยู่"

    s = str(addr).replace("_x000d_", " ")

    # 1) ตามหลัง "จังหวัด / จ." เช่น จ.อุดรธานี
    m = PROV_TAG_RE.search(s)

    if m:
        t = m.group(1)
        for p in PROV_BY_LEN:
            if t.startswith(p):
                return p

    # 2) มีชื่อจังหวัดอยู่ที่ไหนก็ได้ในข้อความ (เช่น TikTok ที่มีแค่ชื่อจังหวัด)
    for p in PROV_BY_LEN:
        if p in s:
            return p

    # 3) กรุงเทพฯ (กทม. / แขวง / Bangkok)
    if BKK_RE.search(s):
        return "กรุงเทพมหานคร"

    return "ไม่ระบุที่อยู่"


def _parse_note(note):
    """หมายเหตุรูปแบบ  วันที่,SETn,รหัส,-,PO.xxx,ข้อความ"""

    out = {
        "วันที่ในหมายเหตุ": pd.NaT,
        "SET": "",
        "รหัส (หมายเหตุ)": "",
        "อ้างอิง PO": "",
    }

    s = "" if pd.isna(note) else str(note)

    m = NOTE_RE.match(s)

    if m:

        d, mo, y = int(m[1]), int(m[2]), int(m[3])

        y = y + 2500 if y < 100 else y
        y = y - 543 if y > 2400 else y

        try:
            out["วันที่ในหมายเหตุ"] = pd.Timestamp(y, mo, d)
        except ValueError:
            pass

        if re.fullmatch(r"SET\d+", m[4].strip(), re.I):
            out["SET"] = m[4].strip().upper()

        code = m[5].strip().upper()

        if re.fullmatch(r"VX\w+|VP\d+|OB\d+", code):
            out["รหัส (หมายเหตุ)"] = code

    p = PO_RE.search(s)

    if p:
        out["อ้างอิง PO"] = p.group(0)

    return out


def _code_kind(code):

    if code.startswith(("VP", "OB")):
        return "รหัสพนักงาน (VP/OB)"

    if code.startswith("VX"):
        return "รหัส VX"

    return ""


def _find_col(df, keywords):

    for c in df.columns:
        if any(k in str(c).lower() for k in keywords):
            return c

    return None


def _prepare(raw):

    df = raw.copy()

    for c in [COL_NOTE, COL_BANK, COL_CUST, COL_NAME, COL_PHONE, COL_DISC,
              COL_ADDR, COL_CANCEL]:
        if c not in df.columns:
            df[c] = pd.NA

    df[COL_ORDER] = df[COL_ORDER].astype(str).str.strip()
    df[COL_SALES] = pd.to_numeric(df[COL_SALES], errors="coerce").fillna(0)
    df[COL_DISC] = pd.to_numeric(df[COL_DISC], errors="coerce").fillna(0)

    df["จังหวัด"] = df[COL_ADDR].map(_province)
    df["ยกเลิก"] = df[COL_CANCEL].astype(str).str.upper().eq("TRUE")

    df["ช่องทาง"] = df[COL_CH].map(_norm_channel)
    df["เพจ/แบรนด์"] = df[COL_CH].map(_page_name)
    df["ประเภท"] = classify_channel(df, COL_CH)["Channel_Category"]

    df["ขนส่ง"] = df[COL_SHIP].fillna("(ไม่ระบุ)").astype(str).str.strip()
    df["ธนาคาร"] = df[COL_BANK].fillna("-").astype(str).str.strip()
    df["COD"] = df["ขนส่ง"].str.contains("COD", case=False)
    df["การชำระ"] = df["COD"].map(
        {True: "COD (เก็บเงินปลายทาง)", False: "ไม่ใช่ COD"}
    )

    df["กลุ่มเลขที่"] = df[COL_ORDER].str.extract(r"^([A-Za-z]+)")[0]

    df["วันที่สร้าง_dt"] = pd.to_datetime(
        df[COL_CREATED] if COL_CREATED in df.columns else pd.NaT,
        format="%d/%m/%Y %H:%M",
        errors="coerce"
    )

    parsed = pd.DataFrame(
        df[COL_NOTE].map(_parse_note).tolist(),
        index=df.index
    )

    df = pd.concat([df, parsed], axis=1)

    df["ชนิดรหัส"] = df["รหัส (หมายเหตุ)"].map(_code_kind)

    # ถ้าไฟล์มีคอลัมน์รหัสสินค้า/จำนวนจริง ให้ใช้แทน
    pcol = _find_col(df, ["รหัสสินค้า", "sku", "product_code"])

    if pcol is not None:
        df["รหัส (หมายเหตุ)"] = df[pcol].fillna("").astype(str)
        df["ชนิดรหัส"] = "รหัสสินค้า"

    qcol = _find_col(df, ["จำนวน", "qty", "quantity"])

    df["จำนวน"] = (
        pd.to_numeric(df[qcol], errors="coerce") if qcol is not None else pd.NA
    )

    return df


def _load(data):

    try:
        raw = pd.read_excel(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        return None, f"อ่านไฟล์ไม่ได้: {e}"

    missing = [c for c in REQUIRED if c not in raw.columns]

    if missing:
        return None, "ไม่ใช่ไฟล์ Shipnity (ขาดคอลัมน์: " + ", ".join(missing) + ")"

    if raw.empty:
        return None, "ไม่มีข้อมูล (มีแต่หัวคอลัมน์)"

    return _prepare(raw), None


def _money(x):
    return f"{x:,.0f}"


def _summ(df, by):

    g = (
        df.groupby(by, dropna=False)
        .agg(ออเดอร์=(COL_ORDER, "count"), ยอดขาย=(COL_SALES, "sum"))
        .reset_index()
    )

    g["เฉลี่ย/ออเดอร์"] = (g["ยอดขาย"] / g["ออเดอร์"]).round(2)
    g["% ยอดขาย"] = (g["ยอดขาย"] / max(df[COL_SALES].sum(), 1) * 100).round(1)

    return g.sort_values("ยอดขาย", ascending=False)


def _first_valid(s):
    """ค่าแรกที่ไม่ว่าง (ใช้เลือกชื่อ/จังหวัดของลูกค้า 1 รหัส)"""

    s = s.dropna()
    s = s[s.astype(str).str.strip() != ""]

    return s.iloc[0] if len(s) else "-"


def _insights(df):

    out = []

    def add(level, title, detail, sub):

        if sub is not None and len(sub):
            label = title if level == "🔵" else f"{title} — {len(sub):,} รายการ"
            out.append((level, label, detail, sub))

    non_mkt = ~df["ช่องทาง"].isin(MARKET)

    add("🔴", "ออเดอร์ยอดขาย 0 บาท",
        "ตรวจว่าเป็นของแถม/ตัวอย่าง หรือคีย์ผิด",
        df[df[COL_SALES] <= 0])

    add("🔴", "ไม่ระบุขนส่ง",
        "ออเดอร์ยังไม่มีขนส่ง อาจส่งไม่ได้หรือบันทึกไม่ครบ",
        df[df["ขนส่ง"] == "(ไม่ระบุ)"])

    add("🔴", "เลขที่ออเดอร์ไม่สอดคล้องกับช่องทาง",
        "ขึ้นต้น RE แต่ช่องทางเป็น Marketplace หรือขึ้นต้น M* แต่เป็นช่องทางแชท/โทร",
        df[
            ((df["กลุ่มเลขที่"] == "RE") & df["ช่องทาง"].isin(MARKET))
            | ((df["กลุ่มเลขที่"] != "RE") & non_mkt)
        ])

    d = df[df[COL_CUST].notna()]
    d = d[d.duplicated([COL_CUST, COL_SALES], keep=False)]

    add("🟡", "สงสัยออเดอร์ซ้ำ (ลูกค้ารหัสเดียวกัน ยอดเท่ากัน)",
        "อาจกดสั่งซ้ำ ควรตรวจก่อนส่ง",
        d.sort_values([COL_CUST, COL_SALES]))

    paid_cod = df[non_mkt & df["COD"] & df["ธนาคาร"].isin(PAID_BANKS)]

    add("🔵", f"ขนส่งชื่อ COD แต่ธนาคารระบุรับเงินแล้ว {len(paid_cod):,} ออเดอร์ (แชท/โทร)",
        "พบเป็นจำนวนมากจนน่าจะเป็นชื่อบริการขนส่ง ไม่ใช่ข้อผิดพลาด — "
        "ควรยืนยันกับทีมว่าคอลัมน์ขนส่งกับธนาคารใช้ความหมายนี้ "
        "ก่อนนำยอด COD ไปตามเก็บเงิน",
        paid_cod)

    add("🟡", "ระบุจ่ายทีหลัง/COD แต่ขนส่งไม่ใช่ COD",
        "เฉพาะช่องทางแชท/โทร — อาจเลือกขนส่งผิดประเภท",
        df[non_mkt & ~df["COD"] & df["ธนาคาร"].str.contains("COD|จ่ายทีหลัง", regex=True)])

    add("🟡", "ช่องทางแชท/โทรที่ไม่มีเบอร์โทรลูกค้า",
        "ติดต่อลูกค้าไม่ได้ถ้าส่งไม่สำเร็จ",
        df[non_mkt & df[COL_PHONE].isna()])

    add("🟡", "ออเดอร์รอสินค้าเข้า",
        "หมายเหตุมีคำว่า “รอสินค้าเข้า” — ยอดค้างส่ง",
        df[df[COL_NOTE].astype(str).str.contains("รอสินค้าเข้า")])

    gap = (df["วันที่ในหมายเหตุ"] - df["วันที่สร้าง_dt"].dt.normalize()).dt.days

    add("🟡", "วันที่ในหมายเหตุห่างจากวันสร้างเกิน 7 วัน",
        "อาจเป็นนัดส่ง/วันที่พิมพ์ผิด ควรตรวจ",
        df[gap > 7])

    add("🟡", "วันที่ในหมายเหตุไม่ถูกต้อง (เช่น 00/00/00)",
        "แก้ให้เป็นวันที่จริง",
        df[df[COL_NOTE].astype(str).str.match(r"^\s*00/00")])

    # ---- ข้อมูลเชิงสรุป ----
    top = _summ(df, ["ช่องทาง"]).iloc[0]

    add("🔵", f"ช่องทางยอดขายสูงสุด: {top['ช่องทาง']} ({top['% ยอดขาย']}% ของยอดขาย)",
        "ช่องทางเดียวที่ถือสัดส่วนสูง = ความเสี่ยงพึ่งพาช่องทางเดียว",
        _summ(df, ["ช่องทาง"]))

    cod = df[df["COD"]]

    add("🔵", f"ขนส่งแบบ COD (ตามชื่อขนส่ง) รวม {_money(cod[COL_SALES].sum())} บาท",
        "นับตามชื่อขนส่งเท่านั้น — ยอดที่ต้องเก็บจริงอาจต่ำกว่านี้ "
        "ถ้าบางออเดอร์รับเงินแล้ว (ดูข้อก่อนหน้า)",
        _summ(cod, ["ขนส่ง"]))

    disc = df[df[COL_DISC] > 0]

    add("🔵", f"ส่วนลด Marketplace รวม {_money(disc[COL_DISC].sum())} บาท",
        "ออเดอร์ที่มีส่วนลดจากแพลตฟอร์ม",
        disc[[COL_ORDER, "ช่องทาง", COL_SALES, COL_DISC]])

    return out
