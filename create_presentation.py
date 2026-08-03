"""
สร้างไฟล์ Presentation สำหรับระบบ EXT CAM POINT AND CALL
รันด้วย: python create_presentation.py
ต้องการ: pip install python-pptx
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
import os

# ── สีธีม ──────────────────────────────────────────────────────────────────
C_BG        = RGBColor(0x0D, 0x1B, 0x2A)   # พื้นหลังเข้ม (navy)
C_BG2       = RGBColor(0x11, 0x28, 0x3E)   # พื้นหลังการ์ด
C_ACCENT    = RGBColor(0x00, 0xC8, 0x53)   # เขียว (primary accent)
C_ACCENT2   = RGBColor(0x00, 0xB0, 0xFF)   # ฟ้า (secondary accent)
C_ORANGE    = RGBColor(0xFF, 0x6D, 0x00)   # ส้ม (warning)
C_WHITE     = RGBColor(0xFF, 0xFF, 0xFF)   # ขาว
C_SUBTEXT   = RGBColor(0x80, 0xA0, 0xC0)   # ฟ้าอ่อน (subtext)
C_YELLOW    = RGBColor(0xFF, 0xD7, 0x00)   # เหลือง (highlight)


# ── Helpers ────────────────────────────────────────────────────────────────

def set_bg(slide, color: RGBColor):
    """ตั้งพื้นหลัง slide เป็นสีทึบ"""
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_textbox(slide, text, left, top, width, height,
                font_size=20, bold=False, color=C_WHITE,
                align=PP_ALIGN.LEFT, italic=False, wrap=True):
    """เพิ่ม textbox และคืน text_frame"""
    txBox = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    tf = txBox.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return tf


def add_rect(slide, left, top, width, height,
             fill_color=None, line_color=None, line_width=Pt(1)):
    """เพิ่ม rectangle shape (card / divider)"""
    from pptx.util import Pt as _Pt
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    if fill_color:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill_color
    else:
        shape.fill.background()

    if line_color:
        shape.line.color.rgb = line_color
        shape.line.width = line_width
    else:
        shape.line.fill.background()
    return shape


def add_divider(slide, top, color=C_ACCENT):
    """เส้นขีดคั่นแนวนอน"""
    add_rect(slide, 0.5, top, 9.0, 0.04, fill_color=color)


def add_bullet_lines(slide, lines, left, top, width, height,
                     font_size=18, color=C_WHITE, spacing=0.42):
    """เพิ่มหลาย bullet line ในพื้นที่เดียว"""
    for i, line in enumerate(lines):
        add_textbox(slide, line,
                    left, top + i * spacing, width, 0.4,
                    font_size=font_size, color=color)


def add_badge(slide, text, left, top, width=1.8, height=0.5,
              bg=C_ACCENT2, fg=C_BG, font_size=13, bold=True):
    """เพิ่ม badge / chip เล็กๆ"""
    add_rect(slide, left, top, width, height, fill_color=bg)
    add_textbox(slide, text,
                left, top + 0.04, width, height,
                font_size=font_size, bold=bold, color=fg,
                align=PP_ALIGN.CENTER)


# ── SLIDES ─────────────────────────────────────────────────────────────────

def slide_01_cover(prs):
    """สไลด์ 1 — หน้าปก"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    set_bg(slide, C_BG)

    # accent bar ซ้าย
    add_rect(slide, 0, 0, 0.12, 7.5, fill_color=C_ACCENT)

    # กล่องชื่อระบบ
    add_rect(slide, 0.4, 1.5, 9.2, 1.1, fill_color=C_BG2)
    add_textbox(slide, "EXT CAM POINT AND CALL",
                0.5, 1.55, 9.0, 1.0,
                font_size=36, bold=True, color=C_ACCENT,
                align=PP_ALIGN.CENTER)

    add_textbox(slide, "ระบบตรวจจับความปลอดภัยด้วย AI",
                0.5, 2.75, 9.0, 0.6,
                font_size=22, bold=False, color=C_WHITE,
                align=PP_ALIGN.CENTER)

    add_textbox(slide, "Real-Time  •  24 ชั่วโมง  •  ไม่ต้องใช้ Internet",
                0.5, 3.3, 9.0, 0.5,
                font_size=15, color=C_SUBTEXT, align=PP_ALIGN.CENTER)

    add_divider(slide, 4.1, color=C_ACCENT2)

    add_textbox(slide, "นำเสนอโดย : ทีมพัฒนาระบบ",
                0.5, 4.3, 9.0, 0.4,
                font_size=14, color=C_SUBTEXT, align=PP_ALIGN.CENTER)
    add_textbox(slide, "สำหรับผู้เยี่ยมชม / ผู้บริหาร",
                0.5, 4.7, 9.0, 0.4,
                font_size=13, color=C_SUBTEXT, align=PP_ALIGN.CENTER)

    # badge เทคโนโลยี
    badges = [("Python", 1.5), ("YOLOv8 AI", 3.5), ("PyQt5 UI", 5.5), ("SQL Server", 7.2)]
    for label, x in badges:
        add_badge(slide, label, x, 5.6, width=1.6, height=0.42,
                  bg=C_BG2, fg=C_ACCENT2, font_size=12)

    add_textbox(slide, "1 / 10",
                8.8, 7.0, 1.0, 0.35,
                font_size=11, color=C_SUBTEXT, align=PP_ALIGN.RIGHT)


def slide_02_problem(prs):
    """สไลด์ 2 — ปัญหา"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    add_rect(slide, 0, 0, 0.12, 7.5, fill_color=C_ORANGE)

    add_textbox(slide, "❗  ปัญหาที่พบในพื้นที่อุตสาหกรรม",
                0.3, 0.25, 9.0, 0.7,
                font_size=26, bold=True, color=C_ORANGE)
    add_divider(slide, 1.05, color=C_ORANGE)

    problems = [
        ("📌", "พนักงานเข้าพื้นที่อันตรายโดยไม่ได้รับอนุญาต",
         "เกิดอุบัติเหตุและความเสียหายที่ป้องกันได้"),
        ("⏱️", "การตรวจสอบด้วยคนใช้เวลานาน และเกิด Human Error",
         "ผู้ควบคุมไม่สามารถดูได้ทุกจุดพร้อมกัน"),
        ("📂", "ไม่มีหลักฐานบันทึกเมื่อเกิดเหตุการณ์",
         "ยากต่อการสืบสวนและปรับปรุงกระบวนการ"),
        ("🔔", "แจ้งเตือนไม่ทันเวลา",
         "กว่าจะรู้ก็สายเกินแก้"),
    ]

    for i, (icon, title, sub) in enumerate(problems):
        y = 1.3 + i * 1.3
        add_rect(slide, 0.4, y, 9.2, 1.1, fill_color=C_BG2,
                 line_color=C_ORANGE)
        add_textbox(slide, icon, 0.55, y + 0.08, 0.6, 0.5, font_size=22)
        add_textbox(slide, title, 1.2, y + 0.05, 8.2, 0.45,
                    font_size=17, bold=True, color=C_WHITE)
        add_textbox(slide, sub, 1.2, y + 0.5, 8.2, 0.45,
                    font_size=13, color=C_SUBTEXT)

    add_textbox(slide, "2 / 10", 8.8, 7.0, 1.0, 0.35,
                font_size=11, color=C_SUBTEXT, align=PP_ALIGN.RIGHT)


def slide_03_solution(prs):
    """สไลด์ 3 — Solution Overview"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    add_rect(slide, 0, 0, 0.12, 7.5, fill_color=C_ACCENT)

    add_textbox(slide, "✅  วิธีแก้ปัญหาของเรา",
                0.3, 0.25, 9.0, 0.7,
                font_size=26, bold=True, color=C_ACCENT)
    add_divider(slide, 1.05)

    solutions = [
        ("🎥", "ใช้กล้อง IP / RTSP ที่มีอยู่แล้ว",        "ไม่ต้องลงทุนซื้ออุปกรณ์ใหม่"),
        ("🤖", "AI วิเคราะห์ภาพ Real-Time ตลอด 24 ชม.",  "ตรวจได้ทุกจุดพร้อมกัน ไม่เหนื่อย ไม่พลาด"),
        ("🚨", "แจ้งเตือนผ่าน Microsoft Teams ทันที",     "ทีมงานรับรู้เหตุการณ์ภายในวินาที"),
        ("💾", "บันทึกรูปภาพ + ฐานข้อมูล อัตโนมัติ",     "มีหลักฐานครบทุกเหตุการณ์"),
        ("📊", "ดูประวัติและรายงานย้อนหลังได้ทุกเวลา",   "Export CSV ส่งต่อได้ทันที"),
    ]

    for i, (icon, title, sub) in enumerate(solutions):
        y = 1.25 + i * 1.1
        add_rect(slide, 0.4, y, 9.2, 1.0, fill_color=C_BG2,
                 line_color=C_ACCENT)
        add_textbox(slide, icon, 0.55, y + 0.1, 0.6, 0.5, font_size=20)
        add_textbox(slide, title, 1.2, y + 0.05, 8.2, 0.42,
                    font_size=17, bold=True, color=C_WHITE)
        add_textbox(slide, sub, 1.2, y + 0.48, 8.2, 0.38,
                    font_size=13, color=C_SUBTEXT)

    add_textbox(slide, "3 / 10", 8.8, 7.0, 1.0, 0.35,
                font_size=11, color=C_SUBTEXT, align=PP_ALIGN.RIGHT)


def slide_04_tech(prs):
    """สไลด์ 4 — เทคโนโลยีที่ใช้"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    add_rect(slide, 0, 0, 0.12, 7.5, fill_color=C_ACCENT2)

    add_textbox(slide, "🛠️  เทคโนโลยีที่ใช้พัฒนา",
                0.3, 0.25, 9.0, 0.7,
                font_size=26, bold=True, color=C_ACCENT2)
    add_divider(slide, 1.05, color=C_ACCENT2)

    techs = [
        ("🐍", "Python 3.12",          "ภาษาหลักในการพัฒนา",           C_YELLOW),
        ("🖥️", "PyQt5",                "UI ทันสมัย ใช้งานง่าย",         C_ACCENT2),
        ("🤖", "YOLOv8 (Ultralytics)", "AI ตรวจจับและติดตามคน",        C_ACCENT),
        ("📷", "OpenCV",               "ประมวลผลภาพจากกล้อง",          C_ACCENT2),
        ("🗄️", "Microsoft SQL Server", "ฐานข้อมูลบันทึกเหตุการณ์",    C_ORANGE),
        ("📢", "Teams Webhook",        "แจ้งเตือนทีมงานแบบ Real-Time", C_SUBTEXT),
    ]

    cols = [(0.35, 0), (5.1, 0)]
    for i, (icon, name, desc, color) in enumerate(techs):
        col = i % 2
        row = i // 2
        x = cols[col][0]
        y = 1.35 + row * 1.85
        w = 4.5

        add_rect(slide, x, y, w, 1.65, fill_color=C_BG2, line_color=color)
        add_textbox(slide, icon, x + 0.15, y + 0.18, 0.7, 0.7, font_size=24)
        add_textbox(slide, name, x + 0.9, y + 0.12, w - 1.0, 0.5,
                    font_size=16, bold=True, color=color)
        add_textbox(slide, desc, x + 0.9, y + 0.62, w - 1.0, 0.7,
                    font_size=13, color=C_SUBTEXT)

    add_textbox(slide, "💡  ทำงานบน Windows  •  ไม่ต้องใช้ Internet",
                0.4, 7.0, 9.0, 0.38,
                font_size=13, color=C_YELLOW, align=PP_ALIGN.CENTER)


def slide_05_ui(prs):
    """สไลด์ 5 — UI Overview"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    add_rect(slide, 0, 0, 0.12, 7.5, fill_color=C_ACCENT)

    add_textbox(slide, "🖥️  หน้าตาระบบ (UI)",
                0.3, 0.25, 9.0, 0.7,
                font_size=26, bold=True, color=C_ACCENT)
    add_divider(slide, 1.05)

    # mock UI layout
    add_rect(slide, 0.4, 1.2, 1.9, 5.5, fill_color=RGBColor(0x0A, 0x14, 0x22),
             line_color=C_ACCENT2)
    add_textbox(slide, "เมนูด้านซ้าย",
                0.45, 1.25, 1.8, 0.4,
                font_size=11, bold=True, color=C_ACCENT2, align=PP_ALIGN.CENTER)

    menus = ["📡  มอนิเตอร์", "⚙️  ตั้งค่า", "🔍  สแกนกล้อง",
             "🚧  โซนอันตราย", "📊  รายงาน"]
    for i, m in enumerate(menus):
        bg = C_ACCENT if i == 0 else C_BG2
        fg = C_BG if i == 0 else C_SUBTEXT
        add_rect(slide, 0.45, 1.75 + i * 0.8, 1.8, 0.65,
                 fill_color=bg, line_color=None)
        add_textbox(slide, m, 0.5, 1.8 + i * 0.8, 1.7, 0.5,
                    font_size=12, bold=(i == 0), color=fg)

    # content area
    add_rect(slide, 2.4, 1.2, 7.2, 5.5,
             fill_color=RGBColor(0x08, 0x12, 0x1F), line_color=C_ACCENT2)
    add_textbox(slide, "📡  พื้นที่แสดงภาพกล้อง (Live Feed)",
                2.5, 1.3, 7.0, 0.45,
                font_size=13, bold=True, color=C_ACCENT2)

    # mock camera feed area
    add_rect(slide, 2.5, 1.85, 5.0, 3.2,
             fill_color=RGBColor(0x05, 0x0E, 0x1A), line_color=C_SUBTEXT)
    add_textbox(slide, "[ ภาพกล้อง Live ]\n🟢 Zone 1   👤 IN ZONE: 2",
                2.6, 2.8, 4.8, 1.3,
                font_size=15, color=C_SUBTEXT, align=PP_ALIGN.CENTER)

    # stats cards
    stats = [("0", "INTRUSIONS", C_ACCENT), ("2", "IN ZONE", C_ACCENT2), ("22", "FPS", C_YELLOW)]
    for i, (val, label, col) in enumerate(stats):
        x = 7.65 + i * 0.0
        add_rect(slide, 7.7, 1.85 + i * 1.15, 1.8, 1.0,
                 fill_color=C_BG2, line_color=col)
        add_textbox(slide, val, 7.7, 1.9 + i * 1.15, 1.8, 0.55,
                    font_size=24, bold=True, color=col, align=PP_ALIGN.CENTER)
        add_textbox(slide, label, 7.7, 2.42 + i * 1.15, 1.8, 0.35,
                    font_size=10, color=C_SUBTEXT, align=PP_ALIGN.CENTER)

    add_textbox(slide, "🎨  Dark Theme  •  เหมาะกับโรงงาน  •  มองเห็นชัดทุกสภาพแสง",
                0.4, 7.0, 9.2, 0.38,
                font_size=13, color=C_SUBTEXT, align=PP_ALIGN.CENTER)


def slide_06_point_call(prs):
    """สไลด์ 6 — Point & Call"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    add_rect(slide, 0, 0, 0.12, 7.5, fill_color=C_YELLOW)

    add_textbox(slide, "👆  ฟังก์ชัน 1 : Point & Call",
                0.3, 0.25, 9.0, 0.7,
                font_size=26, bold=True, color=C_YELLOW)
    add_divider(slide, 1.05, color=C_YELLOW)
    add_textbox(slide, "ระบบตรวจสอบ 'ชี้และพูด' ก่อนเริ่มงานในพื้นที่อันตราย",
                0.4, 1.15, 9.2, 0.45,
                font_size=15, color=C_SUBTEXT)

    # steps flow
    steps = [
        ("1", "พนักงานยืนหน้ากล้อง", C_ACCENT2),
        ("2", "AI ตรวจจับ\nท่าทางการชี้", C_ACCENT),
        ("3", "ตรวจสอบว่า\n'พูดตาม' หรือไม่", C_YELLOW),
        ("4", "บันทึกผล\n✅ PASS  ❌ FAIL", C_ORANGE),
    ]
    for i, (num, label, color) in enumerate(steps):
        x = 0.4 + i * 2.35
        add_rect(slide, x, 1.75, 2.1, 2.2, fill_color=C_BG2, line_color=color)
        # number circle (simulated)
        add_rect(slide, x + 0.7, 1.85, 0.7, 0.7, fill_color=color)
        add_textbox(slide, num, x + 0.7, 1.85, 0.7, 0.7,
                    font_size=20, bold=True, color=C_BG, align=PP_ALIGN.CENTER)
        add_textbox(slide, label, x + 0.1, 2.7, 1.9, 1.1,
                    font_size=14, color=C_WHITE, align=PP_ALIGN.CENTER)

        if i < 3:
            add_textbox(slide, "→", x + 2.15, 2.5, 0.3, 0.5,
                        font_size=22, color=C_SUBTEXT, align=PP_ALIGN.CENTER)

    add_rect(slide, 0.4, 4.2, 9.2, 2.5, fill_color=C_BG2)
    add_textbox(slide, "📌  ประโยชน์ที่ได้รับ",
                0.6, 4.3, 8.8, 0.45,
                font_size=15, bold=True, color=C_YELLOW)
    benefits = [
        "✔️  สร้างวินัยด้านความปลอดภัยให้พนักงาน",
        "✔️  บันทึกหลักฐานผ่าน / ไม่ผ่าน พร้อมภาพและเวลา",
        "✔️  ลดการลืมขั้นตอน Safety Check",
    ]
    add_bullet_lines(slide, benefits, 0.7, 4.85, 8.6, 0.45,
                     font_size=14, color=C_WHITE, spacing=0.5)

    add_textbox(slide, "6 / 10", 8.8, 7.0, 1.0, 0.35,
                font_size=11, color=C_SUBTEXT, align=PP_ALIGN.RIGHT)


def slide_07_zone(prs):
    """สไลด์ 7 — No-Entry Zone"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    add_rect(slide, 0, 0, 0.12, 7.5, fill_color=C_ORANGE)

    add_textbox(slide, "🚧  ฟังก์ชัน 2 : No-Entry Zone",
                0.3, 0.25, 9.0, 0.7,
                font_size=26, bold=True, color=C_ORANGE)
    add_divider(slide, 1.05, color=C_ORANGE)
    add_textbox(slide, "กำหนดโซนอันตรายบนหน้าจอ  —  แจ้งเตือนทันทีที่มีคนเข้า",
                0.4, 1.15, 9.2, 0.45,
                font_size=15, color=C_SUBTEXT)

    # left: steps
    steps = [
        ("1️⃣", "วาดเส้นขอบเขตบนหน้าจอได้เลย"),
        ("2️⃣", "ตั้งชื่อโซน เช่น 'เครื่องจักรอันตราย'"),
        ("3️⃣", "AI ตรวจจับคนใน Real-Time ทุกเฟรม"),
        ("4️⃣", "เมื่อมีคนเข้า → แจ้งเตือน + บันทึกทันที"),
    ]
    for i, (icon, text) in enumerate(steps):
        y = 1.75 + i * 0.88
        add_rect(slide, 0.4, y, 5.5, 0.75, fill_color=C_BG2, line_color=C_ORANGE)
        add_textbox(slide, icon, 0.55, y + 0.08, 0.55, 0.55, font_size=18)
        add_textbox(slide, text, 1.15, y + 0.12, 4.6, 0.5,
                    font_size=15, color=C_WHITE)

    # right: alert features
    add_rect(slide, 6.1, 1.75, 3.4, 3.6, fill_color=C_BG2, line_color=C_ORANGE)
    add_textbox(slide, "⚡  เมื่อเกิดเหตุการณ์",
                6.2, 1.85, 3.2, 0.45,
                font_size=14, bold=True, color=C_ORANGE, align=PP_ALIGN.CENTER)
    alerts = [
        "🔴  เส้นขอบโซนเปลี่ยนสีแดง",
        "📸  ถ่ายภาพหลักฐานอัตโนมัติ",
        "💾  บันทึกลงฐานข้อมูล",
        "📢  แจ้งเตือน MS Teams",
        "🪪  แสดงหมายเลข Track ID",
    ]
    for i, a in enumerate(alerts):
        add_textbox(slide, a, 6.2, 2.45 + i * 0.56, 3.1, 0.5,
                    font_size=13, color=C_WHITE)

    add_textbox(slide, "7 / 10", 8.8, 7.0, 1.0, 0.35,
                font_size=11, color=C_SUBTEXT, align=PP_ALIGN.RIGHT)


def slide_08_rtsp(prs):
    """สไลด์ 8 — RTSP Scanner"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    add_rect(slide, 0, 0, 0.12, 7.5, fill_color=C_ACCENT2)

    add_textbox(slide, "📡  ฟังก์ชัน 3 : RTSP Camera Scanner",
                0.3, 0.25, 9.0, 0.7,
                font_size=26, bold=True, color=C_ACCENT2)
    add_divider(slide, 1.05, color=C_ACCENT2)
    add_textbox(slide, "ค้นหากล้องในเครือข่ายอัตโนมัติ  —  ใช้งานได้ทันที",
                0.4, 1.15, 9.2, 0.45,
                font_size=15, color=C_SUBTEXT)

    features = [
        ("🔍", "สแกนหากล้องทุกตัวใน LAN",
         "กดปุ่มเดียว ระบบหาครบ ไม่ต้องกรอก IP เอง"),
        ("🖼️", "แสดงภาพ Preview ก่อนเลือก",
         "เห็นภาพจริงจากกล้องก่อนตัดสินใจ"),
        ("🌐", "กรอก IP เองสำหรับกล้องต่างเครือข่าย",
         "รองรับกล้องที่ต่อผ่าน LAN Cable คนละ Subnet"),
        ("💾", "บันทึกเป็น Profile ใช้ซ้ำได้",
         "เลือกกล้องเดิมได้เลยในครั้งต่อไป ไม่ต้องสแกนใหม่"),
    ]

    for i, (icon, title, sub) in enumerate(features):
        col = i % 2
        row = i // 2
        x = 0.35 + col * 4.85
        y = 1.75 + row * 2.3
        add_rect(slide, x, y, 4.6, 2.1, fill_color=C_BG2, line_color=C_ACCENT2)
        add_textbox(slide, icon, x + 0.2, y + 0.2, 0.7, 0.7, font_size=26)
        add_textbox(slide, title, x + 1.0, y + 0.18, 3.4, 0.5,
                    font_size=16, bold=True, color=C_ACCENT2)
        add_textbox(slide, sub, x + 1.0, y + 0.68, 3.4, 0.9,
                    font_size=13, color=C_SUBTEXT)

    add_textbox(slide, "⏱️  ค้นหาแต่ละกล้องใช้เวลาไม่เกิน 5 วินาที",
                0.4, 6.9, 9.2, 0.38,
                font_size=13, color=C_YELLOW, align=PP_ALIGN.CENTER)

    add_textbox(slide, "8 / 10", 8.8, 7.0, 1.0, 0.35,
                font_size=11, color=C_SUBTEXT, align=PP_ALIGN.RIGHT)


def slide_09_history(prs):
    """สไลด์ 9 — History & Report"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    add_rect(slide, 0, 0, 0.12, 7.5, fill_color=C_ACCENT)

    add_textbox(slide, "📊  ฟังก์ชัน 4 : รายงานและประวัติเหตุการณ์",
                0.3, 0.25, 9.0, 0.7,
                font_size=26, bold=True, color=C_ACCENT)
    add_divider(slide, 1.05)
    add_textbox(slide, "ดูย้อนหลังได้ทุกเหตุการณ์  •  ภาพหลักฐาน  •  Export ได้ทันที",
                0.4, 1.15, 9.2, 0.45,
                font_size=15, color=C_SUBTEXT)

    # mock table
    add_rect(slide, 0.4, 1.7, 6.0, 0.45, fill_color=C_ACCENT2)
    headers = ["วันที่/เวลา", "ประเภท", "โซน", "ผลลัพธ์"]
    widths  = [1.8, 1.1, 1.5, 1.4]
    cx = 0.5
    for h, w in zip(headers, widths):
        add_textbox(slide, h, cx, 1.72, w, 0.4,
                    font_size=12, bold=True, color=C_BG, align=PP_ALIGN.CENTER)
        cx += w

    rows = [
        ("2026-07-02  14:45",  "INTRUSION", "Zone 1",   "🔴 INTRUSION"),
        ("2026-07-02  14:30",  "PASS",      "-",        "✅ PASS"),
        ("2026-07-02  13:55",  "FAIL",      "-",        "❌ FAIL"),
        ("2026-07-02  11:20",  "INTRUSION", "Zone 2",   "🔴 INTRUSION"),
    ]
    for ri, row in enumerate(rows):
        bg = RGBColor(0x0F, 0x22, 0x35) if ri % 2 == 0 else C_BG2
        add_rect(slide, 0.4, 2.18 + ri * 0.52, 6.0, 0.5, fill_color=bg)
        cx2 = 0.5
        colors = [C_WHITE, C_WHITE, C_WHITE,
                  C_ACCENT if "PASS" in row[3]
                  else (C_ORANGE if "FAIL" in row[3] else RGBColor(0xFF, 0x44, 0x44))]
        for val, w, col in zip(row, widths, colors):
            add_textbox(slide, val, cx2, 2.22 + ri * 0.52, w, 0.42,
                        font_size=12, color=col, align=PP_ALIGN.CENTER)
            cx2 += w

    # features right
    add_rect(slide, 6.6, 1.7, 3.0, 4.0, fill_color=C_BG2, line_color=C_ACCENT)
    add_textbox(slide, "ความสามารถ",
                6.7, 1.78, 2.8, 0.42,
                font_size=14, bold=True, color=C_ACCENT, align=PP_ALIGN.CENTER)
    feats = [
        "🔍  กรองตามวันที่",
        "🔍  กรองตามประเภท",
        "🖼️  ดูรูปหลักฐาน",
        "📤  Export CSV",
        "🗄️  SQL Server",
        "📁  CSV Fallback",
    ]
    for i, f in enumerate(feats):
        add_textbox(slide, f, 6.7, 2.3 + i * 0.52, 2.8, 0.45,
                    font_size=13, color=C_WHITE)

    add_textbox(slide, "9 / 10", 8.8, 7.0, 1.0, 0.35,
                font_size=11, color=C_SUBTEXT, align=PP_ALIGN.RIGHT)


def slide_10_summary(prs):
    """สไลด์ 10 — สรุป"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    add_rect(slide, 0, 0, 0.12, 7.5, fill_color=C_ACCENT)

    add_textbox(slide, "🏆  สรุปจุดเด่นของระบบ",
                0.3, 0.25, 9.0, 0.7,
                font_size=26, bold=True, color=C_ACCENT)
    add_divider(slide, 1.05)

    points = [
        ("✅", "ไม่ต้องเพิ่มอุปกรณ์ใหม่",      "ใช้กล้องที่มีอยู่แล้วได้เลย",    C_ACCENT),
        ("🤖", "AI แม่นยำ 24 ชั่วโมง",         "ตรวจได้ทุกจุด ไม่เหนื่อย ไม่พลาด", C_ACCENT2),
        ("📢", "แจ้งเตือน Teams ทันที",         "ทีมงานรับรู้เหตุการณ์ภายในวินาที", C_YELLOW),
        ("📸", "ภาพหลักฐานทุกเหตุการณ์",        "ใช้สืบสวนและปรับปรุงได้จริง",     C_ORANGE),
        ("🚧", "รองรับหลายโซน หลายกล้อง",      "ขยายระบบได้ตามความต้องการ",      C_ACCENT),
        ("👆", "ใช้งานง่าย ไม่ต้องเป็นผู้เชี่ยวชาญ", "UI ใช้งานง่าย มีคู่มือครบ",     C_ACCENT2),
    ]

    for i, (icon, title, sub, color) in enumerate(points):
        col = i % 2
        row = i // 2
        x = 0.35 + col * 4.85
        y = 1.35 + row * 1.65
        add_rect(slide, x, y, 4.6, 1.5, fill_color=C_BG2, line_color=color)
        add_textbox(slide, icon, x + 0.15, y + 0.2, 0.65, 0.65, font_size=22)
        add_textbox(slide, title, x + 0.9, y + 0.12, 3.5, 0.5,
                    font_size=16, bold=True, color=color)
        add_textbox(slide, sub, x + 0.9, y + 0.62, 3.5, 0.7,
                    font_size=13, color=C_SUBTEXT)

    add_divider(slide, 6.55, color=C_ACCENT2)
    add_textbox(slide, "🙏  ขอบคุณสำหรับการรับฟัง  —  พร้อมรับคำถามและข้อเสนอแนะ",
                0.4, 6.65, 9.2, 0.45,
                font_size=15, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

    add_textbox(slide, "10 / 10", 8.8, 7.0, 1.0, 0.35,
                font_size=11, color=C_SUBTEXT, align=PP_ALIGN.RIGHT)


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    prs = Presentation()
    prs.slide_width  = Inches(10)
    prs.slide_height = Inches(7.5)

    print("กำลังสร้างสไลด์...")
    slide_01_cover(prs)       ; print("  ✔  สไลด์ 1  — หน้าปก")
    slide_02_problem(prs)     ; print("  ✔  สไลด์ 2  — ปัญหา")
    slide_03_solution(prs)    ; print("  ✔  สไลด์ 3  — Solution")
    slide_04_tech(prs)        ; print("  ✔  สไลด์ 4  — เทคโนโลยี")
    slide_05_ui(prs)          ; print("  ✔  สไลด์ 5  — UI")
    slide_06_point_call(prs)  ; print("  ✔  สไลด์ 6  — Point & Call")
    slide_07_zone(prs)        ; print("  ✔  สไลด์ 7  — No-Entry Zone")
    slide_08_rtsp(prs)        ; print("  ✔  สไลด์ 8  — RTSP Scanner")
    slide_09_history(prs)     ; print("  ✔  สไลด์ 9  — รายงาน")
    slide_10_summary(prs)     ; print("  ✔  สไลด์ 10 — สรุป")

    out = "EXT_CAM_Presentation.pptx"
    prs.save(out)
    print(f"\n✅  บันทึกสำเร็จ → {os.path.abspath(out)}")
    print("   เปิดด้วย Microsoft PowerPoint หรือ LibreOffice Impress ได้เลย")


if __name__ == "__main__":
    main()
