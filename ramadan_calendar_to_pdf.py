import argparse
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional

import os
import uuid
import tempfile
from datetime import datetime

import requests
import pgeocode
from pypdf import PdfReader, PdfWriter

from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.colors import HexColor

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ============================================================
# 1) ONLY EDIT THIS SECTION (PLACEMENT / LOOK)
# ============================================================

# Turn ON to draw a red rectangle showing exactly where the table will fill.
DEBUG_DRAW_GREEN_BOX = False

# These are RELATIVE to the PDF page size, so it works for 34x44, letter, etc.
# They define the SOLID GREEN RECTANGLE area you want to fill.
#
# If you need to fine-tune later:
# - Increase LEFT/RIGHT to move inward (more padding from patterned sides)
# - Increase BOTTOM to move up (more space above lanterns)
# - Increase TOP to move down (more space below the header)
GREEN_BOX_LEFT = 0.1   # 14.5% in from left
GREEN_BOX_RIGHT = 0.1  # 14.5% in from right
GREEN_BOX_BOTTOM = 0.14  # 20.5% up from bottom
GREEN_BOX_TOP = 0.35     # 28.5% down from top

# Title inside the green area
DRAW_TITLE = True
TITLE_TEXT_SIZE_RATIO = 0.018  # relative to page height
TITLE_GAP_RATIO = 0.03         # vertical gap between title and table

# Table fonts (relative to page height for large posters)
HEADER_FONT_RATIO = 0.0105
BODY_FONT_RATIO = 0.0092

# General table text color (good contrast on dark green)
TABLE_TEXT_BODY_COLOR = HexColor("#2C542B")
TABLE_TEXT_HEAD_COLOR = colors.whitesmoke
HEADER_BG = colors.Color(0.12, 0.20, 0.12)  # dark green header strip

# ============================================================
# 2) DO NOT EDIT BELOW UNLESS YOU WANT ADVANCED CHANGES
# ============================================================

# Make template/font paths robust for Render / servers
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_PATH = os.path.join(BASE_DIR, "template.pdf")
ARABIC_FONT_NAME = "Janna LT Bold"
ARABIC_FONT_FILE = os.path.join(BASE_DIR, "Janna LT Bold.ttf")

FONT = "Helvetica-Bold"
FONT_BOLD = "Helvetica-Bold"


def setup_arabic_font():
    """Register an Arabic TTF font for proper glyph support."""
    if not os.path.exists(ARABIC_FONT_FILE):
        raise FileNotFoundError(
            f"Arabic font file not found: {ARABIC_FONT_FILE}\n"
            "Put 'Janna LT Bold.ttf' next to this script (same folder), "
            "or update ARABIC_FONT_FILE."
        )
    # Avoid double-register issues on some reloaders
    try:
        pdfmetrics.getFont(ARABIC_FONT_NAME)
    except KeyError:
        pdfmetrics.registerFont(TTFont(ARABIC_FONT_NAME, ARABIC_FONT_FILE))


def ar(text: str) -> str:
    """Shape + bidi Arabic text for correct rendering in ReportLab."""
    if not text:
        return ""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


def to_arabic_indic_digits(s: str) -> str:
    """Convert Western digits to Arabic-Indic digits."""
    trans = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
    return s.translate(trans)


WEEKDAY_AR = {
    "Monday": "الاثنين",
    "Tuesday": "الثلاثاء",
    "Wednesday": "الأربعاء",
    "Thursday": "الخميس",
    "Friday": "الجمعة",
    "Saturday": "السبت",
    "Sunday": "الأحد",
}

# Column order requested:
# Ramadan Day #, Date, Day, Imsak, Fajr, Sunrise, Dhuhr, Asr, Maghrib, Isha
COLS = [
    f"Ramadan\n{ar('رمضان')}",
    f"Date\n{ar('التاريخ')}",
    f"Day\n{ar('اليوم')}",
    f"Imsak\n{ar('إمساك')}",
    f"Fajr\n{ar('الفجر')}",
    f"Sunrise\n{ar('الشروق')}",
    f"Dhuhr\n{ar('الظهر')}",
    f"Asr\n{ar('العصر')}",
    f"Maghrib\n{ar('المغرب')}",
    f"Isha\n{ar('العشاء')}",
]

MAGHRIB_COL_INDEX = 8


@dataclass
class Location:
    zip_code: str
    latitude: float
    longitude: float
    place_name: str
    state_code: str


def clean_time(t: str) -> str:
    if not t:
        return ""
    time_part = t.split(" ")[0].strip()
    try:
        dt = datetime.strptime(time_part, "%H:%M")
        return dt.strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return time_part


def zip_to_latlon_us(zip_code: str) -> Location:
    nomi = pgeocode.Nominatim("us")
    rec = nomi.query_postal_code(zip_code[:5])

    if rec is None or rec.latitude is None or rec.longitude is None:
        raise ValueError(f"Could not resolve ZIP code: {zip_code}")

    return Location(
        zip_code=zip_code[:5],
        latitude=float(rec.latitude),
        longitude=float(rec.longitude),
        place_name=str(rec.place_name) if rec.place_name is not None else "",
        state_code=str(rec.state_code) if rec.state_code is not None else "",
    )


def fetch_month_calendar(
    lat: float,
    lon: float,
    year: int,
    month: int,
    method: int,
    timezone: Optional[str],
    dst_policy: str,  # "LOCK" or "DST"
) -> List[Dict[str, Any]]:
    url = "https://api.aladhan.com/v1/calendar"
    params = {
        "latitude": lat,
        "longitude": lon,
        "method": method,
        "month": month,
        "year": year,
    }

    if timezone:
        params["timezonestring"] = timezone

    # NOTE: This keeps your original behavior exactly.
    # (Even though the comment is confusing, we keep it to preserve output.)
    if dst_policy.upper() == "DST":
        params["dst"] = 0

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    if data.get("code") != 200:
        raise RuntimeError(f"AlAdhan API error: {data}")

    return data["data"]


def extract_ramadan_days(cal_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for day in cal_data:
        hijri = day.get("date", {}).get("hijri", {})
        month_num = hijri.get("month", {}).get("number")
        if month_num == 9:
            out.append(day)
    return out


def get_ramadan_2026(
    lat: float,
    lon: float,
    method: int,
    timezone: Optional[str],
    dst_policy: str,
) -> List[Dict[str, Any]]:
    # Keep your original month fetch (Feb + Mar) to match your existing output/template
    feb = fetch_month_calendar(lat, lon, 2026, 2, method, timezone, dst_policy)
    mar = fetch_month_calendar(lat, lon, 2026, 3, method, timezone, dst_policy)

    ram = extract_ramadan_days(feb) + extract_ramadan_days(mar)

    def greg_key(d):
        g = d["date"]["gregorian"]
        return (int(g["year"]), int(g["month"]["number"]), int(g["day"]))

    ram.sort(key=greg_key)
    return ram


def build_table_data(ramadan_days: List[Dict[str, Any]]) -> List[List[str]]:
    data: List[List[str]] = [COLS]

    for idx, d in enumerate(ramadan_days, start=1):
        g = d["date"]["gregorian"]
        weekday_en = g["weekday"]["en"]
        weekday_ar = WEEKDAY_AR.get(weekday_en, "")

        date_str = f'{g["month"]["en"]} {g["day"]}, {g["year"]}'

        timings = d.get("timings", {})

        ramadan_day_bilingual = f"{idx} / {to_arabic_indic_digits(str(idx))}"
        day_bilingual = f"{weekday_en} / {ar(weekday_ar)}" if weekday_ar else weekday_en

        row = [
            ramadan_day_bilingual,
            date_str,
            day_bilingual,
            clean_time(timings.get("Imsak", "")),
            clean_time(timings.get("Fajr", "")),
            clean_time(timings.get("Sunrise", "")),
            clean_time(timings.get("Dhuhr", "")),
            clean_time(timings.get("Asr", "")),
            clean_time(timings.get("Maghrib", "")),
            clean_time(timings.get("Isha", "")),
        ]
        data.append(row)

    return data


def compute_green_box(page_w: float, page_h: float) -> Tuple[float, float, float, float]:
    x = page_w * GREEN_BOX_LEFT
    y = page_h * GREEN_BOX_BOTTOM
    w = page_w * (1.0 - GREEN_BOX_LEFT - GREEN_BOX_RIGHT)
    h = page_h * (1.0 - GREEN_BOX_BOTTOM - GREEN_BOX_TOP)
    return x, y, w, h


def build_stretched_table(
    table_data: List[List[str]],
    box_w: float,
    box_h: float,
    page_h: float,
    draw_title: bool
) -> Table:
    n_rows = len(table_data)

    # Reserve space for title inside the green box if enabled
    title_gap = (page_h * TITLE_GAP_RATIO) if draw_title else 0.0
    usable_h = box_h - title_gap
    if usable_h <= 0:
        raise RuntimeError("Green box height too small after title gap. Reduce GREEN_BOX_TOP/BOTTOM or TITLE_GAP_RATIO.")

    # Row heights: header a bit taller, body evenly stretched so table fills usable_h exactly
    header_h = usable_h * 0.07
    body_h = (usable_h - header_h) / (n_rows - 1)
    row_heights = [header_h] + [body_h] * (n_rows - 1)

    # Column widths: tuned for readability; sum ~= box_w
    col_widths = [
        box_w * 0.08,   # #
        box_w * 0.15,   # Date
        box_w * 0.15,   # Day
        box_w * 0.085,  # Imsak
        box_w * 0.085,  # Fajr
        box_w * 0.09,   # Sunrise
        box_w * 0.085,  # Dhuhr
        box_w * 0.08,   # Asr
        box_w * 0.10,   # Maghrib
        box_w * 0.095,  # Isha
    ]

    header_font = max(8, int(page_h * HEADER_FONT_RATIO))
    body_font = max(7, int(page_h * BODY_FONT_RATIO))

    t = Table(table_data, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)

    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), ARABIC_FONT_NAME, header_font),
        ("FONT", (0, 1), (-1, -1), ARABIC_FONT_NAME, body_font),

        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

        # Header look
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), TABLE_TEXT_HEAD_COLOR),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.Color(1, 1, 1, alpha=0.6)),

        # Body look
        ("TEXTCOLOR", (0, 1), (-1, -1), TABLE_TEXT_BODY_COLOR),
        ("GRID", (0, 0), (-1, -1), 0.0, colors.Color(1, 1, 1, alpha=0.18)),

        # Padding (kept small; rowHeights control fill)
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    return t


def make_overlay_pdf(
    overlay_path: str,
    page_size: Tuple[float, float],
    title: str,
    table_data: List[List[str]],
) -> None:
    page_w, page_h = page_size
    c = canvas.Canvas(overlay_path, pagesize=page_size)

    # Compute the exact green area box
    box_x, box_y, box_w, box_h = compute_green_box(page_w, page_h)

    # Optional debug: show the exact box being filled
    if DEBUG_DRAW_GREEN_BOX:
        c.setStrokeColor(colors.red)
        c.setLineWidth(6)
        c.rect(box_x, box_y, box_w, box_h, stroke=1, fill=0)

    # Title inside green box (at top of box)
    title_gap = page_h * TITLE_GAP_RATIO if DRAW_TITLE else 0.0
    if DRAW_TITLE:
        title_size = max(10, int(page_h * TITLE_TEXT_SIZE_RATIO))

        # Slight translucent backing band for readability
        c.setFillColor(colors.Color(0, 0, 0, alpha=0.22))
        band_h = title_size * 1.8
        c.rect(box_x, box_y + box_h - band_h, box_w, band_h, fill=1, stroke=0)

        c.setFillColor(colors.whitesmoke)
        c.setFont(FONT_BOLD, title_size)
        c.drawCentredString(box_x + (box_w / 2), box_y + box_h - (band_h * 0.72), title)

    # Build table that fills remaining box height exactly
    t = build_stretched_table(table_data, box_w, box_h, page_h, DRAW_TITLE)

    # Draw table starting from bottom-left of box
    t.wrapOn(c, box_w, box_h - title_gap)
    t.drawOn(c, box_x, box_y)

    c.showPage()
    c.save()


def merge_overlay(template_pdf: str, overlay_pdf: str, output_pdf: str) -> None:
    tpl = PdfReader(template_pdf)
    ovl = PdfReader(overlay_pdf)

    writer = PdfWriter()
    for i, page in enumerate(tpl.pages):
        if i == 0:
            page.merge_page(ovl.pages[0])
        writer.add_page(page)

    with open(output_pdf, "wb") as f:
        writer.write(f)


def run_calendar(
    zip_code: str,
    timezone: Optional[str],
    dst_policy: str = "LOCK",
    method: int = 2,
    out_dir: Optional[str] = None,
    unique_name: bool = True,
) -> str:
    """
    Same layout as your original script, but web-safe output handling.

    - out_dir: where to write the PDF (defaults to system temp dir if not provided)
    - unique_name: avoids collisions when multiple users generate at once
    """
    setup_arabic_font()

    # Read template size
    tpl = PdfReader(TEMPLATE_PATH)
    first_page = tpl.pages[0]
    page_w = float(first_page.mediabox.width)
    page_h = float(first_page.mediabox.height)
    page_size = (page_w, page_h)

    loc = zip_to_latlon_us(zip_code)

    ramadan_days = get_ramadan_2026(
        loc.latitude,
        loc.longitude,
        method=method,
        timezone=timezone,
        dst_policy=dst_policy,
    )
    if not ramadan_days:
        raise RuntimeError("No Ramadan days returned. Try a different method/timezone.")

    table_data = build_table_data(ramadan_days)
    title = f"2026 Ramadan Calendar — {loc.place_name}, {loc.state_code} {loc.zip_code}".strip()

    # Output path
    out_dir = out_dir or tempfile.gettempdir()
    if unique_name:
        token = uuid.uuid4().hex[:10]
        out_pdf = os.path.join(out_dir, f"2026_Ramadan_{loc.zip_code}_{token}.pdf")
    else:
        out_pdf = os.path.join(out_dir, f"2026_Ramadan_{loc.zip_code}.pdf")

    overlay_path = out_pdf + ".overlay.pdf"

    make_overlay_pdf(overlay_path, page_size, title, table_data)
    merge_overlay(TEMPLATE_PATH, overlay_path, out_pdf)

    try:
        os.remove(overlay_path)
    except OSError:
        pass

    return out_pdf


def main():
    ap = argparse.ArgumentParser(description="Create a Ramadan 2026 poster calendar from a PDF template using ZIP code.")
    ap.add_argument("--template", required=False, help="Path to the PDF template (optional; defaults to template.pdf next to script)")
    ap.add_argument("--zip", required=True, help="US ZIP code (5 digits recommended)")
    ap.add_argument("--out", required=False, help="Output PDF path (optional)")
    ap.add_argument("--method", type=int, default=2, help="Prayer time calculation method (default 2)")
    ap.add_argument("--timezone", default=None, help='IANA timezone string (e.g. "America/Chicago")')
    ap.add_argument("--dst", default="DST", choices=["LOCK", "DST"], help='DST behavior')
    ap.add_argument("--no-unique", action="store_true", help="Disable unique naming (may overwrite files).")
    args = ap.parse_args()

    # Allow overriding template path from CLI
    global TEMPLATE_PATH
    if args.template:
        TEMPLATE_PATH = args.template

    setup_arabic_font()

    if args.out:
        out_pdf = args.out
        # Generate using same pipeline but forced output path
        tpl = PdfReader(TEMPLATE_PATH)
        first_page = tpl.pages[0]
        page_size = (float(first_page.mediabox.width), float(first_page.mediabox.height))

        loc = zip_to_latlon_us(args.zip)
        ramadan_days = get_ramadan_2026(
            loc.latitude, loc.longitude,
            method=args.method,
            timezone=args.timezone,
            dst_policy=args.dst
        )
        table_data = build_table_data(ramadan_days)
        title = f"2026 Ramadan Calendar — {loc.place_name}, {loc.state_code} {loc.zip_code}".strip()

        overlay_path = out_pdf + ".overlay.pdf"
        make_overlay_pdf(overlay_path, page_size, title, table_data)
        merge_overlay(TEMPLATE_PATH, overlay_path, out_pdf)

        try:
            os.remove(overlay_path)
        except OSError:
            pass

        print(f"Created: {out_pdf}")
    else:
        out_pdf = run_calendar(
            zip_code=args.zip,
            timezone=args.timezone,
            dst_policy=args.dst,
            method=args.method,
            out_dir=os.getcwd(),
            unique_name=not args.no_unique,
        )
        print(f"Generated: {out_pdf}")


if __name__ == "__main__":
    main()
