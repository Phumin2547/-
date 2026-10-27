"""ดึงออเดอร์จาก Shipnity (GraphQL) แล้วแปลงเป็นตารางหน้าตาเดียวกับไฟล์ Excel ที่ส่งออกจาก Shipnity

ไม่ import streamlit — รับค่าตั้งค่าเข้ามาเป็น dict / ShipnityConfig เพื่อทดสอบได้ง่าย

หลักการ
    1. ใช้ request ที่เบราว์เซอร์ส่งไป Shipnity จริง (เก็บในไฟล์ shipnity_request.json)
       โดยใส่ {{page}} แทนเลขหน้า แล้วโปรแกรมจะไล่ดึงทีละหน้า
    2. Shipnity คืนออเดอร์เรียง "ใหม่ → เก่า" หน้าละ ~14 รายการ (ทั้งระบบมีหลักแสน)
       จึงดึงเฉพาะช่วงวันที่ที่เลือก แล้วหยุดเมื่อทั้งหน้าเก่ากว่าวันเริ่มต้น
    3. แปลงฟิลด์ API → ชื่อคอลัมน์เดียวกับไฟล์ Excel (EXCEL_COLUMNS)
       หน้า "ไฟล์งาน" จึงใช้ _prepare() และแท็บเดิมต่อได้ทันที

การยืนยันตัวตน (ห้ามใส่ในโค้ด / ห้ามส่งขึ้น git)
    .streamlit/secrets.toml
        [shipnity]
        cookie = "..."        # Request Headers → cookie (หรือใช้ token = "...")
        # url = "https://www.shipnity.com/api/graphql"
    หรือ environment variable SHIPNITY_COOKIE / SHIPNITY_TOKEN / SHIPNITY_URL
    หรือวางในช่อง "ตั้งค่าการเชื่อมต่อ" บนหน้าเว็บ (เก็บในหน่วยความจำของ session เท่านั้น)
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import requests

DEFAULT_URL = "https://www.shipnity.com/api/graphql"
DEFAULT_TEMPLATE = str(Path(__file__).with_name("shipnity_request.json"))
PAGE_PLACEHOLDER = "{{page}}"
TZ = "Asia/Bangkok"

# ชื่อคอลัมน์เหมือนไฟล์ Excel ที่ส่งออกจาก Shipnity ทุกตัว (ลำดับเดิม)
EXCEL_COLUMNS = [
    "วันที่สร้าง", "วันที่พิมพ์", "เลขที่ออเดอร์",
    "รหัสลูกค้า (ลูกค้า)", "ชื่อ (ลูกค้า)", "เบอร์โทร (ลูกค้า)", "ที่อยู่ (ลูกค้า)",
    "ยอดขาย", "ค่าส่งที่เก็บลูกค้า", "ยอดขายหักค่าจัดส่ง",
    "ส่วนลดจาก Marketplace", "ยอดขาย-ส่วนลดmarketplace",
    "ช่องทางที่ลูกค้าทักมา", "ขนส่ง", "ธนาคารที่รับเงิน",
    "ยกเลิกออเดอร์แล้ว", "หมายเหตุ",
]

# รหัส orderBank ของ API → ข้อความเดียวกับไฟล์ Excel
# (รหัสที่ไม่อยู่ในนี้จะส่งผ่านตามเดิม และถูกรายงานให้เพิ่มทีหลัง)
BANK_MAP = {
    "pay_later": "จ่ายทีหลัง / COD",
    "shopee": "shopee",
    "tiktok": "tiktok",
    "lazada": "lazada",
    "paysbuy": "Paysbuy",
}

# รหัสชำระเงินที่รับเงินแล้ว (ส่งผ่านตามเดิม ไม่ต้องเตือน)
KNOWN_PAID = {
    "bbl", "kbank", "ktb", "scb", "bay", "ttb", "tmb", "gsb", "kkp", "uob", "cimb", "baac",
    "creditcard", "credit_card", "promptpay", "truemoney", "cash", "transfer",
}

_ZERO_WIDTH = re.compile(r"[​-‍⁠﻿]")


class ShipnityError(Exception):
    """ข้อผิดพลาดที่แสดงให้ผู้ใช้อ่านได้ (ไม่มี cookie/token ในข้อความ)"""


# =========================================================
# ตั้งค่า
# =========================================================

@dataclass
class ShipnityConfig:
    url: str = DEFAULT_URL
    cookie: str = ""
    token: str = ""
    extra_headers: dict = field(default_factory=dict)
    template_path: str = DEFAULT_TEMPLATE
    first_page: int = 1          # เลขหน้าแรกที่ API ใช้ (0 หรือ 1)
    delay: float = 0.0
    workers: int = 8            # ดึงพร้อมกันกี่หน้า (1 = ทีละหน้า)
    per_page: int = 0           # 0 = ใช้ค่าใน request; >14 = ขอหน้าละมากขึ้น (ถ้าเซิร์ฟเวอร์ยอม)           # หน่วงระหว่างหน้า (วินาที) กันยิงถี่เกิน
    timeout: int = 30
    sales_field: str = "price"   # ฟิลด์ที่ใช้เป็น "ยอดขาย" (หรือ "shopReportPrice")
    bank_map: dict = field(default_factory=dict)


# ---------------------------------------------------------
# ใส่ Cookie ตรงนี้ (คัดลอกค่าหลัง "cookie:" จาก Request Headers ของ graphql)
# ⚠️ อย่าอัปโหลดไฟล์นี้ขึ้น GitHub/แชร์ให้คนอื่น เพราะ Cookie = กุญแจเข้าบัญชีร้าน
# ---------------------------------------------------------
SHIPNITY_COOKIE = "_fbp=fb.1.1788258237722.703139044821713611; _tt_enable_cookie=1; _ttp=01M1E7YFFT8TD9TNN6309N1JCE_.tt.1; _hjSessionUser_2218586=eyJpZCI6IjRiM2E2NjRjLWNhNWQtNWNlMi1hZDBlLTVmMjNhOWJhZTQxMiIsImNyZWF0ZWQiOjE3ODgyNTgyMzc3ODIsImV4aXN0aW5nIjp0cnVlfQ==; _ga=GA1.1.1828940005.1788258238; LSW_WEB=LSW_WEB1; ttcsid=1793065224265::lbCqG3_jnp5qxPP1b7Fe.30.1793065251395.0::1.2551.4190::27126.3.0.0::0.0.0; ttcsid_C9JQC23C77U98P8BJL90=1793065224264::yUbXdiLWw-CvnWM2orrZ.30.1793065251395.1; _gcl_au=1.1.1184245558.1788258237.1257018262.1793065247.1793065251.288200068.1793065247.1793065251; remember_user_token=eyJfcmFpbHMiOnsibWVzc2FnZSI6Ilcxc3pNVEF5TlRSZExDSWtNbUVrTVRFa2FHRldhMmRSTDNBM1NTOUZPV3B3UVZadFRtZEdUeUlzSWpFM09UTXdOalV5TlRJdU1UQTBNRGcxSWwwPSIsImV4cCI6IjIwMjctMTAtMjdUMDE6NDA6NTIuMTA0WiIsInB1ciI6ImNvb2tpZS5yZW1lbWJlcl91c2VyX3Rva2VuIn19--fd02bae550b94eca95def3cd13980de70f204329; _ga_EC1XPQLSQT=GS2.1.s1793065223$o27$g1$t1793065252$j31$l0$h3471683; _ga_6LKB6NXFFD=GS2.1.s1793065223$o35$g1$t1793065252$j31$l0$h684556040; _ga_F85GY0LMWM=GS2.1.s1793065223$o35$g1$t1793065252$j31$l0$h802297941; _clck=1sismp1%5E2%5Egan%5E0%5E2435; _clsk=1kp47vx%5E1793065254356%5E1%5E1%5Eu.clarity.ms%2Fcollect; CSRF-TOKEN=nlhYXBUO1whOzm-ROqZWVUGE-iHt6P2qn77k9hNe9JMvxu87Rao5kAe2-pplCQL72yh5KSZHmefv82EwC5sFBA; _shipnity_pro_session=Dy%2Bbtq0cZnUp1uIXKrs1V2EEGST2f%2B0k2i4VtQUQ6dPEy8HD6wqwr35GWXhgwm7cTSsdto0gyD7I9vF2WIHUUiq%2BwXIETQJH8Z%2BkkPuB8v%2BOX3ngowIcI49SfCp0B6rfL8Oxl1SD%2Bjgz3IVCT3d%2Bd55%2BUT8BHRF9Iu4N96vbkwYGM7WL6kXgUNMgFVw4S3bJt4fR%2B8q%2FC7WfKtOEZ5RQN34z6CO8tbZ0rt2KqTjGqmTiiZ9%2BDMsAQtIyX2weuQuC9ZnleJEOWJWzmVe1eUKz%2FrvuBy7xWgT3lQIjlI7c%2BhD2IZ3QXKTsDOJ2Ejl5HrBhcw5weMdduTf%2BoC5jpGghbKUhMO4tYVVYVus4OnYUAz9a2Iekb9dOgJR1TOt8J9lQB9%2BRHySxAR8i3hsjNW4GaTOynjSMzRJV3hAAyh3v1HFdMWkbtwPJZsc2NeWM8WKH7Tt9bCsf16dU--m1yGfmUOOiikXzyJ--Pp7YNutLpFFiFdyfuMJLcA%3D%3D"

SHIPNITY_TOKEN = ""   # ถ้าใช้ Authorization แทน Cookie


def build_config(secrets=None, cookie=None, token=None) -> ShipnityConfig:
    """ลำดับความสำคัญ: ค่าที่กรอกบนหน้าเว็บ > secrets.toml > environment"""

    s = dict(secrets or {})
    env = os.environ

    return ShipnityConfig(
        url=str(s.get("url") or env.get("SHIPNITY_URL") or DEFAULT_URL).strip(),
        cookie=str(cookie or SHIPNITY_COOKIE or s.get("cookie") or env.get("SHIPNITY_COOKIE") or "").strip(),
        token=str(token or SHIPNITY_TOKEN or s.get("token") or env.get("SHIPNITY_TOKEN") or "").strip(),
        extra_headers=dict(s.get("extra_headers") or {}),
        template_path=str(s.get("request_file") or DEFAULT_TEMPLATE),
        first_page=int(s.get("first_page", 1)),
        delay=float(s.get("delay", 0.0)),
        workers=max(1, min(16, int(s.get("workers", 8)))),
        per_page=int(s.get("per_page", 0)),
        timeout=int(s.get("timeout", 30)),
        sales_field=str(s.get("sales_field", "price")),
        bank_map={str(k).lower(): str(v) for k, v in dict(s.get("bank_map") or {}).items()},
    )


def _is_latin1(text: str) -> bool:
    try:
        text.encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


def config_problems(cfg: ShipnityConfig) -> list[str]:
    """รายการสิ่งที่ยังไม่ได้ตั้งค่า (ว่าง = พร้อมดึง)"""

    out = []

    if not (cfg.cookie or cfg.token):
        out.append("ยังไม่ได้ใส่ Cookie — เปิดไฟล์ shipnity_api.py แล้ววางค่าที่ SHIPNITY_COOKIE ด้านบนของฟังก์ชัน build_config จากนั้นรีเฟรชหน้า")

    for label, val in (("Cookie", cfg.cookie), ("Token", cfg.token)):
        if val and not _is_latin1(val):
            out.append(
                f"{label} มีตัวอักษรที่ไม่ใช่ภาษาอังกฤษ/ตัวเลข (เช่น ข้อความไทย) — "
                "น่าจะวางผิดค่า ให้คัดลอกค่า cookie จริงจาก Request Headers ของ request graphql "
                "(ขึ้นต้นเช่น _session=...; ...) ไม่ใช่ข้อความอธิบายหรือชื่อช่อง"
            )

    if not Path(cfg.template_path).exists():
        out.append(
            f"ไม่พบไฟล์ request ({Path(cfg.template_path).name}) — "
            "คัดลอก Payload จากเบราว์เซอร์มาบันทึกไว้ข้างไฟล์แอป แล้วใส่ {{page}} แทนเลขหน้า"
        )

    return out


# =========================================================
# เรียก API
# =========================================================

def load_template(path: str) -> str:

    p = Path(path)

    if not p.exists():
        raise ShipnityError(f"ไม่พบไฟล์ request: {p.name}")

    text = p.read_text(encoding="utf-8")

    if PAGE_PLACEHOLDER not in text:
        raise ShipnityError(
            f"ใน {p.name} ไม่พบ {PAGE_PLACEHOLDER} — ให้แทนเลขหน้าใน request ด้วย "
            f"\"{PAGE_PLACEHOLDER}\" (ใน variables) หรือ {PAGE_PLACEHOLDER} (ในข้อความ query)"
        )

    return text


def _body(template: str, page: int, per_page: int = 0, extra=None) -> dict:
    """แทน {{page}} ได้ทั้งแบบ "{{page}}" ใน variables และแบบอยู่ในข้อความ query"""

    text = template.replace(f'"{PAGE_PLACEHOLDER}"', str(page)).replace(PAGE_PLACEHOLDER, str(page))

    for k, v in (extra or {}).items():
        text = text.replace("{{" + k + "}}", str(v))

    try:
        body = json.loads(text)
    except json.JSONDecodeError as e:
        raise ShipnityError(f"ไฟล์ request ไม่ใช่ JSON ที่ถูกต้อง ({e.msg} บรรทัด {e.lineno})") from None

    if isinstance(body.get("variables"), dict):

        # ตัวแปรวันที่ที่ไม่ได้ส่งค่ามา (เช่นโหมดไล่ดึงเอง) → null ไม่ให้ข้อความ {{...}} หลุดไปที่เซิร์ฟเวอร์
        for k in ("startDate", "endDate"):
            if str(body["variables"].get(k, "")).startswith("{{"):
                body["variables"][k] = None

        if per_page:
            body["variables"]["perPage"] = int(per_page)

    return body


def _headers(cfg: ShipnityConfig) -> dict:

    h = {
        "content-type": "application/json",
        "accept": "application/json",
        "user-agent": "Mozilla/5.0 (OrderReconciliation)",
    }

    if cfg.cookie:
        h["cookie"] = " ".join(cfg.cookie.split())

    if cfg.token:
        h["authorization"] = (
            cfg.token if re.match(r"(?i)^(bearer|token)\s", cfg.token) else f"Bearer {cfg.token}"
        )

    h.update({str(k).lower(): str(v) for k, v in cfg.extra_headers.items()})

    return h


def _parse_payload(payload):
    """คืน (nodes, pagesCount, nodesCount) จาก data.dataWorksheetSearch.nodes[*].toResult"""

    if not isinstance(payload, dict):
        raise ShipnityError("รูปแบบคำตอบจาก Shipnity ไม่ถูกต้อง")

    data = payload.get("data")
    errs = payload.get("errors")

    if errs and not data:
        msg = "; ".join(
            str(e.get("message", e) if isinstance(e, dict) else e)[:200] for e in errs[:3]
        )
        raise ShipnityError(f"Shipnity ตอบ error: {msg}")

    sheets = ((data or {}).get("dataWorksheetSearch") or {}).get("nodes")

    if not sheets:

        detail = []

        if errs:
            detail.append("errors: " + "; ".join(
                str(e.get("message", e) if isinstance(e, dict) else e)[:200] for e in errs[:3]
            ))

        ws = (data or {}).get("dataWorksheetSearch") if isinstance(data, dict) else None

        detail.append(f"คีย์ระดับบน={list(payload.keys())[:6]}")
        detail.append(f"data={'null' if data is None else 'มี'}")
        detail.append(f"dataWorksheetSearch={'null' if ws is None else str(ws)[:150]}")

        raise ShipnityError(
            "ไม่พบ data.dataWorksheetSearch.nodes ในคำตอบ (ข้อมูลว่าง) — "
            "มักเกิดจาก Cookie ไม่ครบ/หมดอายุ (เซิร์ฟเวอร์ถือว่ายังไม่ล็อกอิน) "
            "หรือ id ของ worksheet ใน request ไม่ตรง · รายละเอียด: " + " | ".join(detail)
        )

    nodes, pages, total = [], 0, 0

    for w in sheets:
        res = (w or {}).get("toResult") or {}
        nodes += res.get("nodes") or []
        pages = max(pages, int(res.get("pagesCount") or 0))
        total += int(res.get("nodesCount") or 0)

    return nodes, pages, total


def fetch_page(session, cfg: ShipnityConfig, template: str, page: int, extra=None):

    body = _body(template, page, cfg.per_page, extra)

    last = "ไม่ทราบสาเหตุ"

    for attempt in range(3):

        try:
            r = session.post(cfg.url, json=body, headers=_headers(cfg), timeout=cfg.timeout)
        except requests.RequestException as e:
            last = f"เชื่อมต่อ Shipnity ไม่ได้ ({type(e).__name__})"
            time.sleep(0.8 * (attempt + 1))
            continue

        if r.status_code in (401, 403):
            raise ShipnityError(
                f"Shipnity ปฏิเสธการเข้าถึง (HTTP {r.status_code}) — "
                "Cookie/Token อาจหมดอายุ ให้คัดลอกค่าใหม่จากเบราว์เซอร์"
            )

        if r.status_code == 429 or r.status_code >= 500:
            last = f"เซิร์ฟเวอร์ Shipnity ตอบ HTTP {r.status_code}"
            time.sleep(1.5 * (attempt + 1))
            continue

        if r.status_code != 200:
            raise ShipnityError(f"Shipnity ตอบ HTTP {r.status_code}")

        try:
            payload = r.json()
        except ValueError:
            raise ShipnityError(
                "คำตอบไม่ใช่ JSON (อาจถูกส่งกลับไปหน้าล็อกอิน) — ตรวจ Cookie/Token"
            ) from None

        return _parse_payload(payload)

    raise ShipnityError(last)


# =========================================================
# เลือกช่วงเวลา (วัน / ช่วงวัน / ย้อนหลัง / เดือน / ปี)
# =========================================================

THAI_MONTHS = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]

MODE_SINGLE = "วันเดียว"
MODE_RANGE = "ช่วงวันที่"
MODE_LAST = "ย้อนหลัง"
MODE_MONTH = "รายเดือน"
MODE_YEAR = "ทั้งปี"

MODES = [MODE_SINGLE, MODE_RANGE, MODE_LAST, MODE_MONTH, MODE_YEAR]
LAST_UNITS = ["วัน", "สัปดาห์", "เดือน", "ปี"]


def resolve_range(mode, today, *, single=None, start=None, end=None,
                  n=1, unit="วัน", year=None, month=None):
    """คืน (date_from, date_to) เป็น datetime.date ตามโหมดที่เลือก

    วันสิ้นสุดถูกตัดไม่ให้เกินวันนี้ ถ้าช่วงที่เลือกอยู่ในอนาคตทั้งหมดจะ raise ValueError
    ย้อนหลัง N หน่วย นับรวมวันนี้ เช่น 7 วัน = วันนี้ + 6 วันก่อนหน้า
    """

    t = pd.Timestamp(today).normalize()

    if mode == MODE_SINGLE:
        d1 = d2 = pd.Timestamp(single or today)

    elif mode == MODE_RANGE:
        d1 = pd.Timestamp(start or today)
        d2 = pd.Timestamp(end or start or today)

    elif mode == MODE_LAST:

        n = max(int(n), 1)

        if unit == "สัปดาห์":
            d1 = t - pd.Timedelta(days=7 * n - 1)
        elif unit == "เดือน":
            d1 = t - pd.DateOffset(months=n) + pd.Timedelta(days=1)
        elif unit == "ปี":
            d1 = t - pd.DateOffset(years=n) + pd.Timedelta(days=1)
        else:
            d1 = t - pd.Timedelta(days=n - 1)

        d2 = t

    elif mode == MODE_MONTH:

        first = pd.Timestamp(int(year), int(month), 1)

        d1, d2 = first, first + pd.offsets.MonthEnd(0)

    elif mode == MODE_YEAR:

        d1, d2 = pd.Timestamp(int(year), 1, 1), pd.Timestamp(int(year), 12, 31)

    else:
        raise ValueError(f"ไม่รู้จักโหมด: {mode}")

    d1, d2 = d1.normalize(), min(d2.normalize(), t)

    if d1 > t:
        raise ValueError("ช่วงที่เลือกยังไม่ถึง (อยู่ในอนาคต)")

    if d2 < d1:
        raise ValueError("วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่มต้น")

    return d1.date(), d2.date()


# =========================================================
# ดึงตามช่วงวันที่
# =========================================================

def _to_local(s):
    """ISO string → Timestamp เวลาไทยแบบไม่มี tz (None ถ้าอ่านไม่ได้)"""

    if not s:
        return None

    try:
        t = pd.Timestamp(s)
    except (ValueError, TypeError):
        return None

    if t.tzinfo is not None:
        t = t.tz_convert(TZ).tz_localize(None)

    return t


def _order_time(n):
    return _to_local(n.get("createdAt"))


def _order_key(n):
    return n.get("id") or n.get("invoiceNumber")


def fetch_orders(cfg, date_from, date_to, max_pages=300, progress=None, session=None,
                 template_path=None, time_of=None, key_of=None, raw=False,
                 slack_hours=0, backup_pages=1):
    """ดึงออเดอร์ที่สร้างระหว่าง date_from..date_to (รวมทั้งสองวัน)

    คืน (DataFrame หน้าตาเหมือนไฟล์ Excel, info)
    progress(จำนวนหน้าที่ดึงแล้ว, เวลาออเดอร์เก่าสุดในหน้าล่าสุด) เรียกทุกหน้า
    """

    template = load_template(template_path or cfg.template_path)

    time_of = time_of or _order_time
    key_of = key_of or _order_key

    start = pd.Timestamp(date_from).normalize()
    end = pd.Timestamp(date_to).normalize() + pd.Timedelta(days=1)

    if end <= start:
        raise ShipnityError("วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่มต้น")

    sess = session or requests.Session()

    slack = pd.Timedelta(hours=slack_hours)     # เผื่อลำดับไม่เรียงเป๊ะ (หยุดช้าลงเล็กน้อย)

    kept, seen = [], set()

    info = {
        "pages": 0,
        "fetched": 0,
        "kept": 0,
        "total_in_system": 0,
        "reached_start": False,
        "capped": False,
        "warnings": [],
        "probes": 0,
        "first_page_times": [],
    }

    from concurrent.futures import ThreadPoolExecutor

    first = cfg.first_page
    workers = max(1, int(cfg.workers))
    page = first
    pages_count = 0
    done = False
    jumped = False
    first_oldest = None

    def consume(nodes):
        """ประมวลผลหน้าหนึ่ง → True ถ้าถึงออเดอร์ที่เก่ากว่าวันเริ่มต้นแล้ว"""

        times = [time_of(n) for n in nodes]
        valid = [t for t in times if t is not None]

        nonlocal first_oldest

        if info["pages"] == 1 and valid:
            first_oldest = min(valid)

        if info["pages"] == 1:
            info["first_page_times"] = [f"{t:%d/%m %H:%M}" for t in valid[:14]]

        # เตือนเฉพาะเมื่อเรียงจาก "เก่า → ใหม่" ชัดเจน (เรียงไม่เป๊ะเล็กน้อยถือว่าปกติ)
        if info["pages"] == 1 and len(valid) > 1 and valid[0] < valid[-1] - pd.Timedelta(hours=1):
            info["warnings"].append(
                "Shipnity ไม่ได้เรียงออเดอร์จากใหม่ไปเก่า — การหยุดดึงอัตโนมัติอาจทำให้ข้อมูลไม่ครบ "
                "ลองเลือกช่วงวันที่กว้างขึ้นหรือตรวจการเรียงลำดับใน request"
            )

        for n, t in zip(nodes, times):

            key = key_of(n)

            if key is not None and key in seen:      # ออเดอร์ใหม่ที่เข้ามาระหว่างดึงจะดันหน้า ทำให้เจอซ้ำ
                continue

            if key is not None:
                seen.add(key)

            info["fetched"] += 1

            if t is not None and start <= t < end:
                kept.append(n)

        if progress and valid:
            progress(info["pages"], min(valid))

        return bool(valid) and all(t < start - slack for t in valid)

    with ThreadPoolExecutor(max_workers=workers) as pool:

        while not done:

            if info["pages"] >= max_pages:
                info["capped"] = True
                break

            # ช่วงที่อยู่ในอดีต: ข้ามหน้าใหม่ ๆ ด้วยการหาแบบแบ่งครึ่ง (ออเดอร์เรียงใหม่→เก่า)
            if page == first + 1 and not jumped and pages_count > 40 and first_oldest is not None \
                    and first_oldest >= end:

                jumped = True
                lo, hi = page, first + pages_count - 1     # หาหน้าแรกที่มีออเดอร์เก่ากว่า end

                while lo < hi:
                    mid = (lo + hi) // 2
                    nodes_m, pc_m, _ = fetch_page(sess, cfg, template, mid)
                    info["probes"] += 1
                    tm = [t for t in (time_of(n) for n in nodes_m) if t is not None]

                    if not tm:
                        hi = mid
                    elif min(tm) < end:
                        hi = mid
                    else:
                        lo = mid + 1

                page = max(page, lo - max(1, int(backup_pages)))   # ถอยกลับกันลำดับเหลื่อมและออเดอร์ใหม่ดันหน้า

            # หน้าแรกดึงเดี่ยวเพื่อรู้จำนวนหน้าทั้งหมด จากนั้นดึงเป็นชุดพร้อมกัน
            size = 1 if page == first else min(workers, max_pages - info["pages"])

            batch = list(range(page, page + size))

            if pages_count:
                batch = [x for x in batch if (x - first) < pages_count]

            if not batch:
                info["reached_start"] = True
                break

            if len(batch) == 1:
                results = [fetch_page(sess, cfg, template, batch[0])]
            else:
                results = list(pool.map(lambda x: fetch_page(sess, cfg, template, x), batch))

            for nodes, pc, total in results:      # ประมวลผลตามลำดับหน้าเสมอ

                info["pages"] += 1
                info["total_in_system"] = total or info["total_in_system"]
                pages_count = pc or pages_count

                if not nodes:
                    info["reached_start"] = True
                    done = True
                    break

                if consume(nodes):
                    info["reached_start"] = True
                    done = True
                    break

            page = batch[-1] + 1

            if pages_count and (page - first) >= pages_count:
                info["reached_start"] = True
                break

            if cfg.delay and not done:
                time.sleep(cfg.delay)

    info["kept"] = len(kept)

    if info["capped"]:
        info["warnings"].append(
            f"ดึงครบ {max_pages:,} หน้าแล้วแต่ยังไม่ถึงวันที่เริ่มต้น — ข้อมูลอาจไม่ครบ "
            "เพิ่ม “จำนวนหน้าสูงสุด” หรือเลือกช่วงวันที่สั้นลง"
        )

    if raw:                      # ผู้เรียกจัดการแปลงข้อมูลเอง (เช่นรายงานโปรโมชั่น)
        return kept, info

    bank_map = {**BANK_MAP, **cfg.bank_map}

    unmapped = sorted({
        str(n["orderBank"]) for n in kept
        if n.get("orderBank")
        and str(n["orderBank"]).strip().lower() not in bank_map
        and str(n["orderBank"]).strip().lower() not in KNOWN_PAID
    })

    if unmapped:
        info["warnings"].append(
            "พบรหัสธนาคาร/วิธีชำระที่ยังไม่รู้จัก: " + ", ".join(unmapped)
            + " — ถ้าเป็นการชำระที่รับเงินแล้ว ให้เพิ่มใน BANK_MAP (shipnity_api.py) "
            "เพื่อให้ Insight เรื่อง COD คำนวณถูก"
        )

    mismatch = sum(
        abs(_num(n.get("price")) - _num(n.get("shopReportPrice"))) > 0.005 for n in kept
    )

    if mismatch:
        info["warnings"].append(
            f"พบ {mismatch:,} ออเดอร์ที่ price ไม่เท่ากับ shopReportPrice — ตอนนี้ใช้ “{cfg.sales_field}” "
            "เป็นยอดขาย ถ้าไม่ตรงกับไฟล์ Excel ให้ตั้ง sales_field ใน secrets.toml"
        )

    return to_frame(kept, cfg), info


def fetch_server_range(cfg, date_from, date_to, template_path, max_pages=8000, progress=None,
                       session=None, time_of=None):
    """ให้ Shipnity กรองช่วงวันที่เอง (startDate/endDate แบบเดียวกับหน้าเว็บ) แล้วดึงทุกหน้าพร้อมกัน
    ไม่ต้องไล่ตามลำดับเวลา จึงไม่ขึ้นกับการเรียงลำดับของรายงาน

    คืน (nodes, info)  progress(หน้าที่ดึงแล้ว, หน้าทั้งหมด)
    """

    from concurrent.futures import ThreadPoolExecutor

    d1, d2 = pd.Timestamp(date_from).normalize(), pd.Timestamp(date_to).normalize()

    if d2 < d1:
        raise ShipnityError("วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่มต้น")

    template = load_template(template_path)
    sess = session or requests.Session()
    extra = {"startDate": f"{d1:%Y-%m-%d}", "endDate": f"{d2:%Y-%m-%d}"}
    first = cfg.first_page

    nodes, pages_count, total = fetch_page(sess, cfg, template, first, extra)

    info = {
        "pages": 1, "fetched": len(nodes), "kept": 0, "total_in_system": total,
        "reached_start": True, "capped": False, "warnings": [], "probes": 0,
        "first_page_times": [],
    }

    if time_of and nodes:
        info["first_page_times"] = [
            f"{t:%d/%m %H:%M}" for t in (time_of(n) for n in nodes[:14]) if t is not None
        ]

    last = first + min(pages_count or 1, max_pages) - 1

    if pages_count and pages_count > max_pages:
        info["capped"] = True
        info["warnings"].append(
            f"ช่วงนี้มี {pages_count:,} หน้า แต่ตั้งเพดานไว้ {max_pages:,} หน้า — ข้อมูลไม่ครบ "
            "เลือกช่วงวันที่สั้นลง"
        )

    if progress:
        progress(1, max(pages_count, 1))

    rest = list(range(first + 1, last + 1))

    if rest:

        step = max(1, int(cfg.workers)) * 4

        with ThreadPoolExecutor(max_workers=max(1, int(cfg.workers))) as pool:

            for i in range(0, len(rest), step):

                chunk = rest[i:i + step]

                for n_, _pc, _t in pool.map(
                    lambda x: fetch_page(sess, cfg, template, x, extra), chunk
                ):
                    nodes += n_
                    info["pages"] += 1

                if progress:
                    progress(info["pages"], pages_count)

    info["fetched"] = len(nodes)
    info["kept"] = len(nodes)

    if time_of:

        out = sum(
            1 for n in nodes
            if (t := time_of(n)) is not None and not (d1 <= t.normalize() <= d2)
        )

        if out:
            info["warnings"].append(
                f"มี {out:,} บรรทัดที่เวลาพิมพ์อยู่นอกช่วงที่เลือก (เทียบเวลาไทย) — เซิร์ฟเวอร์กรองวันที่ต่างจากที่แอปคาด"
            )

    return nodes, info


# =========================================================
# แปลง API → ตารางแบบไฟล์ Excel
# =========================================================

def _num(x):

    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0

    return 0.0 if v != v else v


def _txt(x):
    """ข้อความสะอาด (ตัดอักขระความกว้างศูนย์ที่พบในที่อยู่) ค่าว่าง → NA เหมือนเซลล์ว่างใน Excel"""

    if x is None:
        return pd.NA

    s = _ZERO_WIDTH.sub("", str(x)).replace("\xa0", " ").strip()

    return s if s else pd.NA


def _fmt_dt(s):

    t = _to_local(s)

    return t.strftime("%d/%m/%Y %H:%M") if t is not None else pd.NA


def to_frame(nodes, cfg: ShipnityConfig | None = None) -> pd.DataFrame:

    cfg = cfg or ShipnityConfig()

    bank_map = {**BANK_MAP, **cfg.bank_map}

    rows = []

    for n in nodes:

        c = n.get("customer") or {}

        price = _num(n.get(cfg.sales_field))
        fee = _num(n.get("shippingFee"))
        disc = _num(n.get("marketplaceDiscount"))

        bank = _txt(n.get("orderBank"))

        if bank is not pd.NA:
            bank = bank_map.get(bank.lower(), bank)

        printed = _fmt_dt(n.get("printedAt"))

        rows.append({
            "วันที่สร้าง": _fmt_dt(n.get("createdAt")),
            "วันที่พิมพ์": "-" if printed is pd.NA else printed,
            "เลขที่ออเดอร์": _txt(n.get("invoiceNumber")),
            "รหัสลูกค้า (ลูกค้า)": _txt(c.get("invoiceNumber")),
            "ชื่อ (ลูกค้า)": _txt(c.get("name")),
            "เบอร์โทร (ลูกค้า)": _txt(c.get("tel")),
            "ที่อยู่ (ลูกค้า)": _txt(c.get("address")),
            "ยอดขาย": price,
            "ค่าส่งที่เก็บลูกค้า": fee,
            "ยอดขายหักค่าจัดส่ง": round(price - fee, 2),
            "ส่วนลดจาก Marketplace": disc,
            "ยอดขาย-ส่วนลดmarketplace": round(price - disc, 2),
            "ช่องทางที่ลูกค้าทักมา": _txt(n.get("contactMethod")),
            "ขนส่ง": _txt(n.get("shippingType")),
            "ธนาคารที่รับเงิน": bank,
            "ยกเลิกออเดอร์แล้ว": bool(n.get("cancelled")),
            "หมายเหตุ": _txt(n.get("annotation")),
            # คอลัมน์เสริม (ไม่มีในไฟล์ Excel)
            "ยอดขายตามใบรายงาน": _num(n.get("shopReportPrice")),
            "Shipnity ID": _txt(n.get("id")),
        })

    return pd.DataFrame(rows, columns=EXCEL_COLUMNS + ["ยอดขายตามใบรายงาน", "Shipnity ID"])