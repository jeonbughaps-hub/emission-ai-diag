import os
import urllib.request
import re
from datetime import datetime
from typing import Any

from fpdf import FPDF

FONT_FILE_NAME = "NanumGothic-Regular.ttf"
FONT_BOLD_NAME = "NanumGothic-Bold.ttf"
BRAND_NAVY = (24, 43, 73)
BRAND_ACCENT = (48, 112, 176)
BRAND_LIGHT_BG = (245, 248, 252)
BRAND_HEADER_BG = (230, 238, 248)

try:
    from utils import (
        FONT_FILE_NAME as U_FONT, FONT_BOLD_NAME as U_BOLD, 
        BRAND_NAVY as U_NAVY, BRAND_ACCENT as U_ACCENT,
        BRAND_LIGHT_BG as U_BG, BRAND_HEADER_BG as U_HBG, 
        get_env_office, get_limit_ppm,
    )
    if U_FONT: FONT_FILE_NAME = U_FONT
    if U_BOLD: FONT_BOLD_NAME = U_BOLD
    if U_NAVY: BRAND_NAVY = U_NAVY
    if U_ACCENT: BRAND_ACCENT = U_ACCENT
    if U_BG: BRAND_LIGHT_BG = U_BG
    if U_HBG: BRAND_HEADER_BG = U_HBG
except ImportError:
    def get_env_office(addr):
        return "오창읍"
    def get_limit_ppm(ind):
        return "100ppm" if any(x in str(ind).upper() for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]) else "50ppm"

PAGE_W, PAGE_H = 210, 297
LEFT, RIGHT = 10, 200
CONTENT_W = RIGHT - LEFT
BODY_BOTTOM = 277
FONT_REGULAR_URL = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
FONT_BOLD_URL = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"

COLOR_TEXT = (42, 52, 67)
COLOR_MUTED = (105, 117, 134)
COLOR_BORDER = (215, 223, 233)
COLOR_WHITE = (255, 255, 255)
COLOR_GREEN = (37, 132, 91)
COLOR_AMBER = (198, 126, 35)
COLOR_RED = (190, 61, 61)
COLOR_BLUE = (48, 112, 176)
COLOR_GRAY = (135, 145, 157)


def ensure_korean_font():
    try:
        if not os.path.exists(FONT_FILE_NAME):
            urllib.request.urlretrieve(FONT_REGULAR_URL, FONT_FILE_NAME)
        if not os.path.exists(FONT_BOLD_NAME):
            urllib.request.urlretrieve(FONT_BOLD_URL, FONT_BOLD_NAME)
    except Exception as exc:
        print(f"폰트 다운로드 실패: {exc}")


def _safe_text(value: Any, default="-"):
    if value is None: return default
    text = str(value).replace("\r", "").strip()
    return text if text else default


def _as_float(value):
    try: return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError): return None


def get_aqi_status(val, item_type):
    v = _as_float(val)
    if v is None: return "자료 없음", COLOR_GRAY, 0.0
    if item_type == "PM10":
        if v <= 30: return "좋음", (50, 150, 255), min(max(v / 150, 0), 1)
        if v <= 80: return "보통", (60, 180, 110), min(max(v / 150, 0), 1)
        if v <= 150: return "나쁨", COLOR_AMBER, min(max(v / 150, 0), 1)
        return "매우 나쁨", COLOR_RED, 1.0
    if item_type == "O3":
        if v <= 0.030: return "좋음", (50, 150, 255), min(max(v / 0.150, 0), 1)
        if v <= 0.090: return "보통", (60, 180, 110), min(max(v / 0.150, 0), 1)
        if v <= 0.150: return "나쁨", COLOR_AMBER, min(max(v / 0.150, 0), 1)
        return "매우 나쁨", COLOR_RED, 1.0
    return "측정불가", COLOR_GRAY, 0.0


def _grade_color(grade, score=None):
    g = _safe_text(grade, "").upper()
    n = _as_float(score)
    if g in ("A", "우수", "적합"): return COLOR_GREEN
    if g in ("B", "양호"): return COLOR_BLUE
    if g in ("C", "보통", "주의"): return COLOR_AMBER
    if g in ("D", "E", "미흡", "부적합", "위험"): return COLOR_RED
    if n is not None:
        if n >= 90: return COLOR_GREEN
        if n >= 80: return COLOR_BLUE
        if n >= 60: return COLOR_AMBER
        return COLOR_RED
    return COLOR_GRAY


class ProfessionalPDF(FPDF):
    def __init__(self, toc_data=None):
        super().__init__(orientation="P", unit="mm", format="A4")
        self._toc = toc_data or []
        self._section = ""
        self._korean_font_ready = False
        self.set_margins(LEFT, 18, PAGE_W - RIGHT)
        self.set_auto_page_break(auto=True, margin=17)
        self.alias_nb_pages()

    def _fn(self):
        return "Nanum" if self._korean_font_ready else "Arial"

    def _reg_fonts(self):
        ensure_korean_font()
        if os.path.exists(FONT_FILE_NAME):
            try:
                try:
                    self.add_font("Nanum", "", FONT_FILE_NAME, uni=True)
                    bold_src = FONT_BOLD_NAME if os.path.exists(FONT_BOLD_NAME) else FONT_FILE_NAME
                    self.add_font("Nanum", "B", bold_src, uni=True)
                except TypeError:
                    self.add_font("Nanum", "", FONT_FILE_NAME)
                    bold_src = FONT_BOLD_NAME if os.path.exists(FONT_BOLD_NAME) else FONT_FILE_NAME
                    self.add_font("Nanum", "B", bold_src)
                self._korean_font_ready = True
            except Exception as exc:
                print(f"한글 폰트 등록 실패: {exc}")
        return self._fn()

    def header(self):
        if self.page_no() <= 2: return
        fn = self._fn()
        self.set_font(fn, "B", 9)
        self.set_text_color(*BRAND_NAVY)
        self.set_xy(LEFT, 7)
        self.cell(95, 5, "비산배출시설 정밀 자가진단 보고서", 0, 0, "L")
        self.set_xy(105, 7)
        self.set_font(fn, "", 9)
        self.set_text_color(*COLOR_MUTED)
        self.cell(95, 5, _safe_text(self._section, ""), 0, 0, "R")
        self.set_draw_color(*BRAND_ACCENT)
        self.set_line_width(0.35)
        self.line(LEFT, 14, RIGHT, 14)
        self.set_xy(LEFT, 18)

    def footer(self):
        if self.page_no() <= 2: return
        self.set_y(-13)
        y = self.get_y()
        self.set_draw_color(*COLOR_BORDER)
        self.set_line_width(0.25)
        self.line(LEFT, y, RIGHT, y)
        self.set_y(y + 2)
        self.set_font(self._fn(), "", 9)
        self.set_text_color(*COLOR_MUTED)
        self.cell(0, 4, f"- {self.page_no() - 2} -", 0, 0, "C")

    def check_page_break(self, required_height):
        if self.get_y() + required_height > BODY_BOTTOM: self.add_page()

    def draw_cover(self, company, address, industry, permit_no, date_str):
        fn = self._fn()
        self.set_fill_color(*BRAND_LIGHT_BG)
        self.rect(0, 0, PAGE_W, PAGE_H, "F")
        self.set_fill_color(*BRAND_NAVY)
        self.rect(0, 0, PAGE_W, 32, "F")
        self.set_y(10)
        self.set_font(fn, "B", 12)
        self.set_text_color(225, 235, 248)
        self.cell(0, 8, "환경관리 정밀 자가진단 시스템 | 시범 운영 보고서", 0, 1, "C")
        self.set_fill_color(*BRAND_ACCENT)
        self.rect(0, 32, 6, 216, "F")
        self.set_fill_color(*COLOR_WHITE)
        self.set_draw_color(195, 212, 231)
        self.set_line_width(0.45)
        self.rect(16, 45, 178, 176, "FD")
        self.set_fill_color(*BRAND_ACCENT)
        self.rect(16, 45, 178, 20, "F")
        self.set_xy(20, 48)
        self.set_font(fn, "B", 18)
        self.set_text_color(*COLOR_WHITE)
        self.cell(170, 12, "비산배출시설 정밀 자가진단 보고서", 0, 1, "C")
        self.set_y(70)
        self.set_font(fn, "B", 11)
        self.set_text_color(*BRAND_NAVY)
        self.cell(0, 7, "HAPs 비산배출시설 환경관리 적합성 진단", 0, 1, "C")
        self.set_draw_color(*BRAND_ACCENT)
        self.line(25, 80, 190, 80)

        rows = [
            ("진단 대상 사업장", company),
            ("소재지", address),
            ("업종 분류", industry),
            ("허가·신고 번호", permit_no),
            ("보고서 작성일", date_str),
        ]
        start_y, row_h = 90, 16
        for idx, (label, value) in enumerate(rows):
            y = start_y + idx * row_h
            self.set_fill_color(*(BRAND_LIGHT_BG if idx % 2 == 0 else COLOR_WHITE))
            self.rect(22, y, 166, row_h - 1, "F")
            self.set_xy(25, y + 3)
            self.set_font(fn, "B", 11)
            self.set_text_color(*BRAND_NAVY)
            self.cell(43, 8, label, 0, 0, "L")
            self.set_xy(70, y + 3)
            self.set_font(fn, "", 11)
            self.set_text_color(*COLOR_TEXT)
            self.cell(115, 8, _safe_text(value).replace("\n", " "), 0, 0, "L")

        sign_y = 175
        self.set_draw_color(190, 205, 222)
        self.rect(22, sign_y, 166, 30, "D")
        labels = ["진단 담당자", "검토자", "사업장 확인"]
        col_w = 166 / 3
        for idx, label in enumerate(labels):
            x = 22 + idx * col_w
            if idx: self.line(x, sign_y, x, sign_y + 30)
            self.set_xy(x, sign_y + 4)
            self.set_font(fn, "B", 10)
            self.set_text_color(*COLOR_MUTED)
            self.cell(col_w, 8, label, 0, 0, "C")

        self.set_fill_color(*BRAND_ACCENT)
        self.rect(0, 248, PAGE_W, 8, "F")
        self.set_y(249)
        self.set_font(fn, "B", 9)
        self.set_text_color(*COLOR_WHITE)
        self.cell(0, 6, "AI 기반 환경관리 진단 시스템", 0, 0, "C")
        self.set_fill_color(228, 237, 250)
        self.rect(0, 256, PAGE_W, 41, "F")
        self.set_y(264)
        self.set_font(fn, "", 10)
        self.set_text_color(*BRAND_NAVY)
        self.cell(0, 6, f"보고 일자: {date_str} | 자가진단 참고자료", 0, 0, "C")

    def draw_toc(self, toc_items):
        fn = self._fn()
        self.set_fill_color(*BRAND_LIGHT_BG)
        self.rect(0, 0, PAGE_W, PAGE_H, "F")
        self.set_fill_color(*BRAND_NAVY)
        self.rect(0, 0, PAGE_W, 25, "F")
        self.set_y(6)
        self.set_font(fn, "B", 14)
        self.set_text_color(225, 235, 248)
        self.cell(0, 12, "목 차  |  CONTENTS", 0, 1, "C")
        self.ln(10)
        for title, page in toc_items:
            is_sub = str(title).startswith("  ")
            self.set_x(23 if is_sub else 16)
            self.set_font(fn, "" if is_sub else "B", 11 if is_sub else 12)
            self.set_text_color(*(COLOR_MUTED if is_sub else BRAND_NAVY))
            self.cell(160 if is_sub else 170, 9, str(title).strip(), 0, 0, "L")
            self.cell(0, 9, str(page or "-"), 0, 1, "R")
            self.set_draw_color(222, 228, 236)
            y = self.get_y() - 1
            self.line(16, y, 194, y)
            self.ln(1)

    def draw_section_header(self, txt, set_section=True):
        fn = self._fn()
        if set_section: self._section = txt
        self.check_page_break(25)
        self.ln(4)
        y = self.get_y()
        self.set_fill_color(*BRAND_ACCENT)
        self.rect(LEFT, y, 4, 12, "F")
        self.set_font(fn, "B", 15)
        self.set_text_color(*BRAND_NAVY)
        self.set_xy(LEFT + 7, y + 1)
        self.cell(0, 10, txt, 0, 1, "L")
        self.set_draw_color(*BRAND_ACCENT)
        self.set_line_width(0.4)
        self.line(LEFT, y + 14, RIGHT, y + 14)
        self.set_y(y + 18)

    def draw_sub_header(self, txt):
        fn = self._fn()
        self.check_page_break(18)
        self.ln(3)
        self.set_font(fn, "B", 11.5)
        self.set_text_color(*BRAND_ACCENT)
        self.set_x(LEFT + 1)
        self.cell(0, 8, txt, 0, 1, "L")
        self.ln(1)

    def _wrap_text(self, text, max_width, font_size):
        self.set_font(self._fn(), "", font_size)
        text = _safe_text(text)
        result = []
        for paragraph in text.split("\n"):
            if not paragraph.strip():
                result.append("")
                continue
            
            words = paragraph.split(' ')
            current_line = ""
            
            for word in words:
                if self.get_string_width(current_line + word + " ") > max_width:
                    if current_line:
                        result.append(current_line.strip())
                        current_line = word + " "
                    else:
                        current_char_line = ""
                        for char in word:
                            if self.get_string_width(current_char_line + char) > max_width:
                                result.append(current_char_line)
                                current_char_line = char
                            else:
                                current_char_line += char
                        current_line = current_char_line + " "
                else:
                    current_line += word + " "
            
            if current_line.strip():
                result.append(current_line.strip())
                
        return result if result else ["-"]

    def draw_zebra_table(self, headers, rows, col_widths):
        fn = self._fn()
        if not headers or not col_widths: return
        table_width = sum(col_widths)
        x0 = LEFT
        base_font_size = 9.0
        line_h = 5.0
        pad_x, pad_y = 2.0, 2.5
        bottom_limit = BODY_BOTTOM

        def draw_header():
            y = self.get_y()
            x = x0
            self.set_font(fn, "B", 10.0)
            self.set_text_color(*BRAND_NAVY)
            self.set_fill_color(*BRAND_HEADER_BG)
            self.set_draw_color(185, 201, 220)
            heights = []
            wrapped_headers = []
            for title, width in zip(headers, col_widths):
                lines = self._wrap_text(title, width - 2 * pad_x, 10.0)
                wrapped_headers.append(lines)
                heights.append(max(10, len(lines) * line_h + 4))
            header_h = max(heights)
            for lines, width in zip(wrapped_headers, col_widths):
                self.rect(x, y, width, header_h, "DF")
                self.set_xy(x + pad_x, y + 2)
                self.multi_cell(width - 2 * pad_x, line_h, "\n".join(lines), 0, "C")
                x += width
            self.set_xy(x0, y + header_h)

        if not rows:
            self.set_font(fn, "", base_font_size)
            self.set_text_color(*COLOR_MUTED)
            self.set_fill_color(*BRAND_LIGHT_BG)
            self.cell(table_width, 11, "자료 없음 — 입력 또는 추출된 데이터가 없습니다.", 1, 1, "C", True)
            self.ln(2)
            return

        draw_header()
        for row_idx, row in enumerate(rows):
            values = list(row[:len(headers)])
            values.extend(["-"] * (len(headers) - len(values)))
            
            cell_fonts = []
            wrapped_cells = []
            
            for idx, (val, w) in enumerate(zip(values, col_widths)):
                c_font = base_font_size
                val_str = str(val)
                
                if any(keyword in str(headers[idx]) for keyword in ["측정일", "구분", "점검 연도"]):
                    val_str = val_str.replace('\n', '').replace(' ', '').strip()
                    
                tokens = val_str.replace('\n', ' ').split()
                
                while c_font > 5.0:
                    self.set_font(fn, "", c_font)
                    if any(self.get_string_width(tok) > w - 2 * pad_x for tok in tokens):
                        c_font -= 0.5
                        continue
                    
                    wrapped = self._wrap_text(val_str, w - 2 * pad_x, c_font)
                    if len(wrapped) <= 3:
                        break
                    c_font -= 0.5
                
                cell_fonts.append(c_font)
                wrapped_cells.append(self._wrap_text(val_str, w - 2 * pad_x, c_font))
            
            row_h = max(10, max(len(lines) for lines in wrapped_cells) * line_h + 2 * pad_y)

            if self.get_y() + row_h > bottom_limit:
                self.add_page()
                draw_header()

            y, x = self.get_y(), x0
            for idx, (width, lines, c_font) in enumerate(zip(col_widths, wrapped_cells, cell_fonts)):
                fill = BRAND_LIGHT_BG if row_idx % 2 else COLOR_WHITE
                self.set_fill_color(*fill)
                self.set_draw_color(*COLOR_BORDER)
                self.rect(x, y, width, row_h, "DF")
                self.set_font(fn, "", c_font)
                self.set_text_color(*COLOR_TEXT)
                self.set_xy(x + pad_x, y + pad_y)
                header_name = str(headers[idx])
                align = "C" if any(k in header_name for k in ("판정", "등급", "우선순위", "결과", "확인", "기준")) else "L"
                self.multi_cell(width - 2 * pad_x, line_h, "\n".join(lines), 0, align)
                x += width
            self.set_xy(x0, y + row_h)
        self.ln(3)

    def draw_visual_scorecard(self, scores_data):
        fn = self._fn()
        scores_data = scores_data if isinstance(scores_data, dict) else {}
        self.check_page_break(45)
        start_y = self.get_y()
        blocks = [
            ("관리자 선임", scores_data.get("manager_score")),
            ("방지시설 기준", scores_data.get("prevention_score")),
            ("LDAR 점검", scores_data.get("ldar_score")),
            ("기록 충실성", scores_data.get("record_score")),
        ]
        overall = scores_data.get("overall_score")
        overall = overall if isinstance(overall, dict) else {}
        gap, overall_w = 3, 50
        block_w = (CONTENT_W - 4 * gap - overall_w) / 4
        x = LEFT

        for title, item in blocks:
            item = item if isinstance(item, dict) else {}
            score = _as_float(item.get("score"))
            grade = _safe_text(item.get("grade"), "미산정")
            color = _grade_color(grade, score)
            self.set_fill_color(*COLOR_WHITE)
            self.set_draw_color(*COLOR_BORDER)
            self.rect(x, start_y, block_w, 33, "FD")
            self.set_fill_color(*color)
            self.rect(x, start_y, block_w, 2.5, "F")
            self.set_xy(x + 1.5, start_y + 5)
            self.set_font(fn, "", 9)
            self.set_text_color(*COLOR_MUTED)
            self.cell(block_w - 3, 5, title, 0, 0, "C")
            self.set_xy(x + 1, start_y + 12)
            self.set_font(fn, "B", 20)
            self.set_text_color(*BRAND_NAVY)
            self.cell(block_w - 2, 9, f"{score:g}" if score is not None else "-", 0, 0, "C")
            self.set_xy(x + 1, start_y + 24)
            self.set_font(fn, "B", 9)
            self.set_text_color(*color)
            self.cell(block_w - 2, 5, grade, 0, 0, "C")
            x += block_w + gap

        overall_score = _as_float(overall.get("score"))
        overall_grade = _safe_text(overall.get("grade"), "미산정")
        overall_color = _grade_color(overall_grade, overall_score)
        self.set_fill_color(*BRAND_LIGHT_BG)
        self.set_draw_color(*COLOR_BORDER)
        self.rect(x, start_y, overall_w, 33, "FD")
        self.set_fill_color(*overall_color)
        self.rect(x, start_y, overall_w, 2.5, "F")
        self.set_xy(x + 1, start_y + 4)
        self.set_font(fn, "", 9.5)
        self.set_text_color(*COLOR_MUTED)
        self.cell(overall_w - 2, 5, "종합 결과", 0, 0, "C")
        self.set_xy(x + 1, start_y + 10)
        self.set_font(fn, "B", 18)
        self.set_text_color(*overall_color)
        self.cell(overall_w - 2, 10, overall_grade, 0, 0, "C")
        self.set_xy(x + 1, start_y + 23)
        self.set_font(fn, "", 9)
        self.set_text_color(*BRAND_NAVY)
        label = f"총점 {overall_score:g}점" if overall_score is not None else "총점 미산정"
        self.cell(overall_w - 2, 5, label, 0, 0, "C")
        self.set_y(start_y + 38)
        self.set_font(fn, "", 9)
        self.set_text_color(*COLOR_MUTED)
        self.multi_cell(0, 5, "※ 자료 미확보 항목은 적합으로 간주하지 않으며, 추가 확인이 필요합니다.")
        self.ln(2)

    def draw_air_quality_infographic(self, station_name, air_data):
        fn = self._fn()
        air_data = air_data if isinstance(air_data, dict) else {}
        self.check_page_break(60)
        start_y = self.get_y()
        pm10, o3 = air_data.get("pm10Value", "-"), air_data.get("o3Value", "-")
        pm_status, pm_color, pm_ratio = get_aqi_status(pm10, "PM10")
        o3_status, o3_color, o3_ratio = get_aqi_status(o3, "O3")
        self.set_fill_color(245, 248, 252)
        self.set_draw_color(*COLOR_BORDER)
        self.rect(LEFT, start_y, CONTENT_W, 52, "DF")
        self.set_xy(LEFT + 5, start_y + 4)
        self.set_font(fn, "B", 11)
        self.set_text_color(*BRAND_NAVY)
        self.cell(CONTENT_W - 10, 6, f"지역 대기질 참고 정보 | 측정소: {_safe_text(station_name)}", 0, 1, "L")

        cards = [
            (LEFT + 5, "오존 (O3)", o3, "ppm", o3_status, o3_color, o3_ratio, "참고값 0.09"),
            (LEFT + 98, "미세먼지 (PM10)", pm10, "㎍/㎥", pm_status, pm_color, pm_ratio, "참고값 80"),
        ]
        for x, label, value, unit, status, color, ratio, reference in cards:
            y = start_y + 14
            self.set_fill_color(*COLOR_WHITE)
            self.set_draw_color(*COLOR_BORDER)
            self.rect(x, y, 87, 34, "DF")
            self.set_xy(x + 4, y + 4)
            self.set_font(fn, "B", 10)
            self.set_text_color(*COLOR_TEXT)
            self.cell(48, 6, label, 0, 0, "L")
            self.set_xy(x + 4, y + 12)
            self.set_font(fn, "B", 16)
            self.set_text_color(*BRAND_NAVY)
            self.cell(50, 8, f"{_safe_text(value)} {unit}", 0, 0, "L")
            self.set_fill_color(*color)
            self.rect(x + 61, y + 4, 21, 7, "F")
            self.set_xy(x + 61, y + 5)
            self.set_font(fn, "B", 9)
            self.set_text_color(*COLOR_WHITE)
            self.cell(21, 5, status, 0, 0, "C")
            bar_x, bar_y, bar_w = x + 4, y + 26, 75
            self.set_fill_color(230, 235, 240)
            self.rect(bar_x, bar_y, bar_w, 3, "F")
            self.set_fill_color(*color)
            self.rect(bar_x, bar_y, bar_w * ratio, 3, "F")
            self.set_xy(bar_x, y + 29.5)
            self.set_font(fn, "", 8.5)
            self.set_text_color(*COLOR_MUTED)
            self.cell(bar_w, 4, reference, 0, 0, "L")

        self.set_y(start_y + 56)
        self.set_font(fn, "", 9)
        self.set_text_color(*COLOR_MUTED)
        self.multi_cell(0, 5, "※ 지역 대기질은 참고 정보이며, 사업장 배출시설의 법적 준수 여부를 직접 판정하지 않습니다.")
        self.ln(2)

    def draw_text_box(self, text: str, title: str = ""):
        fn = self._fn()
        if title:
            self.check_page_break(18)
            self.set_font(fn, "B", 11)
            self.set_text_color(*BRAND_NAVY)
            self.cell(0, 8, title, 0, 1, "L")

        content = _safe_text(text, "")
        if not content or content == "-":
            self.set_fill_color(*BRAND_LIGHT_BG)
            self.set_font(fn, "", 10.5)
            self.set_text_color(*COLOR_MUTED)
            self.multi_cell(0, 7, "해당 내용이 입력되지 않았습니다. 관련 자료를 확인해 주세요.", 0, "L", True)
            self.ln(3)
            return

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                self.ln(2)
                continue
            if re.match(r"^【.*】$", line) or re.match(r"^\[.*\]$", line):
                self.check_page_break(15)
                self.ln(2)
                self.set_font(fn, "B", 11)
                self.set_text_color(*BRAND_NAVY)
                self.multi_cell(0, 7, line, 0, "L")
            elif re.match(r"^(?:\d+[.)]|[-•✓])\s*", line):
                self.check_page_break(12)
                self.set_font(fn, "", 10.5)
                self.set_text_color(*COLOR_TEXT)
                self.set_x(LEFT + 4)
                self.multi_cell(CONTENT_W - 4, 6.5, line, 0, "L")
            else:
                self.set_font(fn, "", 10.5)
                self.set_text_color(*COLOR_TEXT)
                self.set_x(LEFT)
                self.multi_cell(CONTENT_W, 6.5, line, 0, "L")
        self.ln(3)


def _get_rows(data, section, key="data"):
    value = data.get(section, {})
    if not isinstance(value, dict): return []
    rows = value.get(key, [])
    return rows if isinstance(rows, list) else []

def _record_value(record, key, default="-"):
    if not isinstance(record, dict): return default
    return _safe_text(record.get(key), default)


def create_gov_report_pdf(ai_data: dict, user_info: dict, air_advice: str, air_data: dict, station_name: str) -> bytes:
    ai_data = ai_data if isinstance(ai_data, dict) else {}
    user_info = user_info if isinstance(user_info, dict) else {}
    air_data = air_data if isinstance(air_data, dict) else {}
    now_str = datetime.now().strftime("%Y년 %m월 %d일")
    data = ai_data.get("parsed", {})
    data = data if isinstance(data, dict) else {}
    scores = data.get("scores", {})
    scores = scores if isinstance(scores, dict) else {}

    toc_items = [
        ("가. 사업장 및 진단 개요", "본문"),
        ("나. 준수율 종합 스코어카드", "본문"),
        ("다. 지역 대기질 참고 정보", "본문"),
        ("라. 시설별 정밀 진단 내역", "본문"),
        ("마. 위험도 평가 및 행정처분 참고", "본문"),
        ("바. 종합 의견 및 개선 로드맵", "본문"),
        ("사. 관련 규제 및 법령 참고사항", "본문"),
        ("아. 변경신고 및 추진체계", "본문"),
        ("자. 사업장 자가점검표", "본문"),
    ]

    pdf = ProfessionalPDF(toc_data=toc_items)
    pdf._reg_fonts()

    # 표지 및 목차
    pdf.add_page()
    pdf.draw_cover(
        user_info.get("name", "-"), user_info.get("addr", "-"),
        user_info.get("industry", "-"), user_info.get("permit_no", "-"), now_str
    )
    pdf.add_page()
    pdf.draw_toc(toc_items)
    pdf.add_page()

    # 가. 개요
    pdf.draw_section_header("가. 사업장 및 진단 개요")
    pdf.draw_sub_header("1) 기본 정보")
    pdf.draw_zebra_table(
        ["항목", "내용", "항목", "내용"],
        [
            ["사업장명", user_info.get("name", "-"), "소재지", user_info.get("addr", "-")],
            ["업종분류", user_info.get("industry", "-"), "진단일자", now_str],
            ["허가·신고 번호", user_info.get("permit_no", "-"), "관할 측정소", station_name or "-"],
        ],
        [30, 65, 30, 65],
    )
    pdf.draw_sub_header("2) 자료 해석 유의사항")
    pdf.draw_text_box(
        "본 보고서는 입력된 사업장 자료와 시스템 분석 결과를 바탕으로 작성됩니다.\n"
        "자료가 누락되었거나 문서에서 확인되지 않는 항목은 적합으로 간주하지 않고, 추가 확인이 필요한 항목으로 취급해야 합니다.\n"
        "최종 법규 준수 여부 및 행정처분 적용은 관련 법령과 관할 기관의 확인이 필요합니다."
    )

    # 나. 점수
    pdf.draw_section_header("나. 준수율 종합 스코어카드")
    pdf.draw_sub_header("1) 분야별 점수 및 종합 결과")
    pdf.draw_visual_scorecard(scores)

    # 다. 지역 대기질
    pdf.draw_section_header("다. 지역 대기질 참고 정보")
    pdf.draw_air_quality_infographic(station_name, air_data)
    pdf.draw_sub_header("1) VOCs 연계 환경관리 제언")
    pdf.draw_text_box(air_advice)

    # 라. 시설별 결과
    pdf.draw_section_header("라. 시설별 정밀 진단 내역")
    pdf.draw_sub_header("1) 방지시설 배출농도 추이 (THC)")
    prev_rows = [
        [_record_value(p, "period"), _record_value(p, "date"), _record_value(p, "facility"),
         _record_value(p, "value"), _record_value(p, "limit"), _record_value(p, "result")]
        for p in _get_rows(data, "prevention")
    ]
    pdf.draw_zebra_table(["구분", "측정일", "방지시설명", "결과", "기준", "판정"], prev_rows, [13, 27, 39, 50, 43, 18])

    cooling_rows = [
        [_record_value(p, "date"), _record_value(p, "facility"),
         _record_value(p, "value"), _record_value(p, "limit"), _record_value(p, "result")]
        for p in _get_rows(data, "cooling")
    ]
    
    next_idx = 2
    if cooling_rows:
        pdf.draw_sub_header(f"{next_idx}) 냉각탑 및 열교환기 냉각수 TOC 농도 추이")
        pdf.draw_zebra_table(["측정일", "시설명", "결과", "기준", "판정"], cooling_rows, [27, 38, 50, 50, 25])
        next_idx += 1

    pdf.draw_sub_header(f"{next_idx}) 비산누출시설 LDAR 점검 실적")
    ldar_rows = [
        [_record_value(p, "year"), _record_value(p, "target_count"), _record_value(p, "leak_count"),
         _record_value(p, "leak_rate"), _record_value(p, "recheck_done"), _record_value(p, "result")]
        for p in _get_rows(data, "ldar")
    ]
    pdf.draw_zebra_table(
        ["점검 연도", "대상 개소", "누출 수", "누출률", "재측정·조치", "최종 판정"],
        ldar_rows, [22, 28, 20, 25, 55, 40]
    )

    # 마. 위험도
    pdf.draw_section_header("마. 위험도 평가 및 행정처분 참고")
    pdf.draw_sub_header("1) 항목별 위험도 평가")
    risk_rows = []
    risk_data = data.get("risk_matrix", [])
    if isinstance(risk_data, list):
        for item in risk_data:
            if isinstance(item, dict):
                risk_rows.append([
                    _record_value(item, "item"), _record_value(item, "probability"),
                    _record_value(item, "impact"), _record_value(item, "priority")
                ])
    pdf.draw_zebra_table(["위험 항목", "발생 가능성", "영향도", "우선순위"], risk_rows, [58, 42, 40, 50])
    pdf.draw_sub_header("2) 행정처분 검토 시 유의사항")
    pdf.draw_text_box(
        "행정처분은 위반 행위의 구체적 내용, 위반 횟수, 적용 법령, 경감·가중 사유 등에 따라 달라질 수 있습니다.\n"
        "본 보고서의 위험도 또는 예상 시나리오는 사전 검토용 참고자료이며 확정적인 처분 예고나 법률적 판단을 의미하지 않습니다.\n"
        "처분 기준과 과태료 금액은 보고서 작성 시점의 최신 법령 및 관할 기관 안내를 확인해야 합니다."
    )

    # 바. 개선 로드맵
    pdf.draw_section_header("바. 종합 의견 및 개선 로드맵")
    pdf.draw_sub_header("1) 단계별 개선 로드맵")
    roadmap_rows = []
    roadmap = data.get("improvement_roadmap", [])
    if isinstance(roadmap, list):
        for item in roadmap:
            if isinstance(item, dict):
                roadmap_rows.append([
                    _record_value(item, "phase"), _record_value(item, "action"),
                    _record_value(item, "expected_effect")
                ])
    pdf.draw_zebra_table(["단계·기간", "주요 개선 조치", "기대 효과"], roadmap_rows, [30, 92, 68])

    pdf.draw_sub_header("2) AI 정밀 진단 종합 의견")
    pdf.draw_text_box(data.get("overall_opinion", "-"))

    # 사. 법령
    pdf.draw_section_header("사. 관련 규제 및 법령 참고사항")
    pdf.draw_sub_header("1) 벌칙 및 과태료 규정")
    law1 = [
        ["[벌칙] 시설개선 조치명령 미이행자", "5년 이하 징역 또는 5천만원 이하 벌금"], 
        ["[벌칙] 비산배출시설 미신고 설치·운영자", "300만원 이하 벌금"], 
        ["[과태료] 정기점검을 받지 아니한 자", "300만원 이하 과태료"], 
        ["[과태료] 변경신고를 하지 아니한 자", "200만원 이하 과태료"]
    ]
    pdf.draw_zebra_table(["위반 대상", "벌칙 및 과태료 내용"], law1, [80, 110])

    pdf.draw_sub_header("2) 위반 횟수별 가중 행정처분 기준")
    law2 = [
        ["신고/변경신고 미이행", "경고", "경고", "조업정지 10일", "조업정지 20일"], 
        ["시설관리기준 미준수", "경고", "조업정지 10일", "조업정지 20일", "조업정지 20일"], 
        ["정기점검 미수검", "경고", "경고", "조업정지 10일", "조업정지 20일"], 
        ["조치명령 미이행", "조업정지 10일", "조업정지 20일", "조업정지 30일", "조업정지 30일"]
    ]
    pdf.draw_zebra_table(["위반 사항", "1차 처분", "2차 처분", "3차 처분", "4차 처분"], law2, [50, 35, 35, 35, 35])

    # 아. 변경신고 및 후속 조치
    pdf.draw_section_header("아. 변경신고 및 추진체계")
    pdf.draw_sub_header("1) 비산배출시설 의무 변경신고 사유")
    pdf.draw_text_box(
        "※ 비산배출시설을 신고한 사업자는 다음 사유 발생 시 의무적으로 변경신고를 해야 합니다.\n"
        "1. 사업장 명칭 또는 대표자를 변경하는 경우\n"
        "2. 비산배출시설 관리계획을 변경하는 경우\n"
        "3. 비산배출시설을 임대, 증설, 교체 또는 일부 폐쇄하는 경우\n"
        "4. 신고서의 오기, 누락 등 변경사유가 분명한 경우\n"
        "5. 비산배출시설을 완전히 폐쇄하는 경우"
    )

    # 자. 체크리스트
    pdf.draw_section_header("자. 사업장 자가점검표")
    pdf.draw_sub_header("1) 정기 점검 체크리스트")
    checklist = [
        ["□", "일일", "방지시설 가동 상태 및 이상 무 확인"],
        ["□", "일일", "국소배기장치 및 송풍기 가동 여부 확인"],
        ["□", "주간", "차압계 등 계측기 수치와 설계 범위 확인"],
        ["□", "월간", "흡착제 상태 및 교체 필요성 검토"],
        ["□", "반기", "시설관리기준에 따른 정기 점검 자료 확인"],
        ["□", "반기", "LDAR 점검, 누출 수리 및 재측정 기록 확인"],
        ["□", "연간", "보고서 제출 의무와 제출 기한 확인"],
    ]
    pdf.draw_zebra_table(["확인", "주 주기", "점검 항목"], checklist, [20, 30, 140])

    pdf.draw_sub_header("2) 점검 결과 기록 (사업장 보관용)")
    pdf.draw_zebra_table(
        ["점검일", "점검 항목", "결과", "조치 내용", "확인자"],
        [["", "", "", "", ""] for _ in range(4)],
        [25, 55, 25, 55, 30]
    )
    pdf.ln(4)
    pdf.set_font(pdf._fn(), "", 9.5)
    pdf.set_text_color(*COLOR_MUTED)
    pdf.multi_cell(
        0, 5,
        "본 보고서는 사업장 자가진단과 환경관리 개선을 지원하기 위한 참고자료입니다. "
        "입력 자료의 정확성, 최신 법령 적용 여부 및 최종 행정 판단은 별도 확인이 필요합니다."
    )

    output = pdf.output(dest="S")
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)
