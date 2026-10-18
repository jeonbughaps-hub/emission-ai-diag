import os
import urllib.request
import re
from datetime import datetime
from typing import Any

from fpdf import FPDF
from utils import (
    FONT_FILE_NAME, FONT_BOLD_NAME, BRAND_NAVY, BRAND_ACCENT,
    BRAND_LIGHT_BG, BRAND_HEADER_BG, SCORE_COLORS, get_env_office,
    get_limit_ppm,
)

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
    """한글 폰트가 없으면 다운로드를 시도합니다."""
    try:
        if not os.path.exists(FONT_FILE_NAME):
            urllib.request.urlretrieve(FONT_REGULAR_URL, FONT_FILE_NAME)
        if not os.path.exists(FONT_BOLD_NAME):
            urllib.request.urlretrieve(FONT_BOLD_URL, FONT_BOLD_NAME)
    except Exception as exc:
        print(f"폰트 다운로드 실패: {exc}")


def _safe_text(value: Any, default="-"):
    if value is None:
        return default
    text = str(value).replace("\r", "").strip()
    return text if text else default


def _as_float(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def get_aqi_status(val, item_type):
    """지역 대기질 시각화용 분류이며 사업장 법규 준수 판정 기준은 아닙니다."""
    v = _as_float(val)
    if v is None:
        return "자료 없음", COLOR_GRAY, 0.0
    if item_type == "PM10":
        if v <= 30:
            return "좋음", (50, 150, 255), min(max(v / 150, 0), 1)
        if v <= 80:
            return "보통", (60, 180, 110), min(max(v / 150, 0), 1)
        if v <= 150:
            return "나쁨", COLOR_AMBER, min(max(v / 150, 0), 1)
        return "매우 나쁨", COLOR_RED, 1.0
    if item_type == "O3":
        if v <= 0.030:
            return "좋음", (50, 150, 255), min(max(v / 0.150, 0), 1)
        if v <= 0.090:
            return "보통", (60, 180, 110), min(max(v / 0.150, 0), 1)
        if v <= 0.150:
            return "나쁨", COLOR_AMBER, min(max(v / 0.150, 0), 1)
        return "매우 나쁨", COLOR_RED, 1.0
    return "측정불가", COLOR_GRAY, 0.0


def _grade_color(grade, score=None):
    g = _safe_text(grade, "").upper()
    n = _as_float(score)
    if g in ("A", "우수", "적합"):
        return COLOR_GREEN
    if g in ("B", "양호"):
        return COLOR_BLUE
    if g in ("C", "보통", "주의"):
        return COLOR_AMBER
    if g in ("D", "E", "미흡", "부적합", "위험"):
        return COLOR_RED
    if n is not None:
        if n >= 90:
            return COLOR_GREEN
        if n >= 80:
            return COLOR_BLUE
        if n >= 60:
            return COLOR_AMBER
        return COLOR_RED
    return COLOR_GRAY


class ProfessionalPDF(FPDF):
    """공공기관 보고서용 PDF 레이아웃."""

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
        if self.page_no() <= 2:
            return
        fn = self._fn()
        self.set_font(fn, "B", 8)
        self.set_text_color(*BRAND_NAVY)
        self.set_xy(LEFT, 7)
        self.cell(95, 5, "비산배출시설 정밀 자가진단 보고서", 0, 0, "L")
        self.set_xy(105, 7)
        self.set_font(fn, "", 8)
        self.set_text_color(*COLOR_MUTED)
        self.cell(95, 5, _safe_text(self._section, ""), 0, 0, "R")
        self.set_draw_color(*BRAND_ACCENT)
        self.set_line_width(0.35)
        self.line(LEFT, 14, RIGHT, 14)
        self.set_xy(LEFT, 18)

    def footer(self):
        if self.page_no() <= 2:
            return
        self.set_y(-13)
        y = self.get_y()
        self.set_draw_color(*COLOR_BORDER)
        self.set_line_width(0.25)
        self.line(LEFT, y, RIGHT, y)
        self.set_y(y + 2)
        self.set_font(self._fn(), "", 8)
        self.set_text_color(*COLOR_MUTED)
        self.cell(0, 4, f"- {self.page_no() - 2} -", 0, 0, "C")

    def check_page_break(self, required_height):
        if self.get_y() + required_height > BODY_BOTTOM:
            self.add_page()

    def draw_cover(self, company, address, industry, permit_no, date_str):
        fn = self._fn()
        self.set_fill_color(*BRAND_LIGHT_BG)
        self.rect(0, 0, PAGE_W, PAGE_H, "F")
        self.set_fill_color(*BRAND_NAVY)
        self.rect(0, 0, PAGE_W, 29, "F")
        self.set_y(8)
        self.set_font(fn, "B", 10)
        self.set_text_color(225, 235, 248)
        self.cell(0, 8, "환경관리 정밀 자가진단 시스템 | 시범 운영 보고서", 0, 1, "C")
        self.set_fill_color(*BRAND_ACCENT)
        self.rect(0, 29, 6, 219, "F")
        self.set_fill_color(*COLOR_WHITE)
        self.set_draw_color(195, 212, 231)
        self.set_line_width(0.45)
        self.rect(16, 42, 178, 176, "FD")
        self.set_fill_color(*BRAND_ACCENT)
        self.rect(16, 42, 178, 17, "F")
        self.set_xy(20, 45)
        self.set_font(fn, "B", 14)
        self.set_text_color(*COLOR_WHITE)
        self.cell(170, 10, "비산배출시설 정밀 자가진단 보고서", 0, 1, "C")
        self.set_y(64)
        self.set_font(fn, "B", 9)
        self.set_text_color(*BRAND_NAVY)
        self.cell(0, 7, "HAPs 비산배출시설 환경관리 적합성 진단", 0, 1, "C")
        self.set_draw_color(*BRAND_ACCENT)
        self.line(25, 74, 190, 74)

        rows = [
            ("진단 대상 사업장", company),
            ("소재지", address),
            ("업종 분류", industry),
            ("허가·신고 번호", permit_no),
            ("보고서 작성일", date_str),
        ]
        start_y, row_h = 82, 13
        for idx, (label, value) in enumerate(rows):
            y = start_y + idx * row_h
            self.set_fill_color(*(BRAND_LIGHT_BG if idx % 2 == 0 else COLOR_WHITE))
            self.rect(22, y, 166, row_h - 1, "F")
            self.set_xy(25, y + 2)
            self.set_font(fn, "B", 9)
            self.set_text_color(*BRAND_NAVY)
            self.cell(43, 7, label, 0, 0, "L")
            self.set_xy(70, y + 2)
            self.set_font(fn, "", 9)
            self.set_text_color(*COLOR_TEXT)
            self.cell(115, 7, _safe_text(value).replace("\n", " "), 0, 0, "L")

        sign_y = 157
        self.set_draw_color(190, 205, 222)
        self.rect(22, sign_y, 166, 25, "D")
        labels = ["진단 담당자", "검토자", "사업장 확인"]
        col_w = 166 / 3
        for idx, label in enumerate(labels):
            x = 22 + idx * col_w
            if idx:
                self.line(x, sign_y, x, sign_y + 25)
            self.set_xy(x, sign_y + 3)
            self.set_font(fn, "B", 8)
            self.set_text_color(*COLOR_MUTED)
            self.cell(col_w, 6, label, 0, 0, "C")

        self.set_fill_color(*BRAND_ACCENT)
        self.rect(0, 248, PAGE_W, 8, "F")
        self.set_y(249)
        self.set_font(fn, "B", 8)
        self.set_text_color(*COLOR_WHITE)
        self.cell(0, 6, "AI 기반 환경관리 진단 시스템", 0, 0, "C")
        self.set_fill_color(228, 237, 250)
        self.rect(0, 256, PAGE_W, 41, "F")
        self.set_y(264)
        self.set_font(fn, "", 8)
        self.set_text_color(*BRAND_NAVY)
        self.cell(0, 5, f"보고 일자: {date_str} | 자가진단 참고자료", 0, 0, "C")

    def draw_toc(self, toc_items):
        fn = self._fn()
        self.set_fill_color(*BRAND_LIGHT_BG)
        self.rect(0, 0, PAGE_W, PAGE_H, "F")
        self.set_fill_color(*BRAND_NAVY)
        self.rect(0, 0, PAGE_W, 22, "F")
        self.set_y(5)
        self.set_font(fn, "B", 12)
        self.set_text_color(225, 235, 248)
        self.cell(0, 10, "목 차  |  CONTENTS", 0, 1, "C")
        self.ln(7)
        for title, page in toc_items:
            is_sub = str(title).startswith("  ")
            self.set_x(23 if is_sub else 16)
            self.set_font(fn, "" if is_sub else "B", 9 if is_sub else 10)
            self.set_text_color(*(COLOR_MUTED if is_sub else BRAND_NAVY))
            self.cell(160 if is_sub else 170, 7, str(title).strip(), 0, 0, "L")
            self.cell(0, 7, str(page or "-"), 0, 1, "R")
            self.set_draw_color(222, 228, 236)
            y = self.get_y() - 1
            self.line(16, y, 194, y)

    def draw_section_header(self, txt, set_section=True):
        fn = self._fn()
        if set_section:
            self._section = txt
        self.check_page_break(22)
        self.ln(3)
        y = self.get_y()
        self.set_fill_color(*BRAND_ACCENT)
        self.rect(LEFT, y, 3.5, 10, "F")
        self.set_font(fn, "B", 12)
        self.set_text_color(*BRAND_NAVY)
        self.set_xy(LEFT + 6, y + 1)
        self.cell(0, 8, txt, 0, 1, "L")
        self.set_draw_color(*BRAND_ACCENT)
        self.set_line_width(0.35)
        self.line(LEFT, y + 12, RIGHT, y + 12)
        self.set_y(y + 15)

    def draw_sub_header(self, txt):
        fn = self._fn()
        self.check_page_break(14)
        self.ln(2)
        self.set_font(fn, "B", 9.5)
        self.set_text_color(*BRAND_ACCENT)
        self.set_x(LEFT + 1)
        self.cell(0, 7, txt, 0, 1, "L")
        self.ln(1)

    def _wrap_text(self, text, max_width, font_size):
        """한글·영문을 모두 고려해 글자 폭 기준으로 줄바꿈합니다."""
        self.set_font(self._fn(), "", font_size)
        text = _safe_text(text)
        result = []
        for paragraph in text.split("\n"):
            if paragraph == "":
                result.append("")
                continue
            current = ""
            for char in paragraph:
                candidate = current + char
                if current and self.get_string_width(candidate) > max_width:
                    result.append(current)
                    current = char
                else:
                    current = candidate
            result.append(current or " ")
        return result or ["-"]

    def draw_zebra_table(self, headers, rows, col_widths):
        """긴 셀 자동 줄바꿈, 동적 행 높이, 페이지 이동 및 머리글 반복."""
        fn = self._fn()
        if not headers or not col_widths:
            return
        table_width = sum(col_widths)
        x0 = LEFT
        font_size, line_h = 8, 4.4
        pad_x, pad_y = 1.5, 1.8
        bottom_limit = BODY_BOTTOM

        def draw_header():
            y = self.get_y()
            x = x0
            self.set_font(fn, "B", 8)
            self.set_text_color(*BRAND_NAVY)
            self.set_fill_color(*BRAND_HEADER_BG)
            self.set_draw_color(185, 201, 220)
            heights = []
            wrapped_headers = []
            for title, width in zip(headers, col_widths):
                lines = self._wrap_text(title, width - 2 * pad_x, 8)
                wrapped_headers.append(lines)
                heights.append(max(8, len(lines) * 4.2 + 3))
            header_h = max(heights)
            for lines, width in zip(wrapped_headers, col_widths):
                self.rect(x, y, width, header_h, "DF")
                self.set_xy(x + pad_x, y + 1.5)
                self.multi_cell(width - 2 * pad_x, 4.2, "\n".join(lines), 0, "C")
                x += width
            self.set_xy(x0, y + header_h)

        if not rows:
            self.set_font(fn, "", 8.5)
            self.set_text_color(*COLOR_MUTED)
            self.set_fill_color(*BRAND_LIGHT_BG)
            self.cell(table_width, 9, "자료 없음 — 입력 또는 추출된 데이터가 없습니다.", 1, 1, "C", True)
            return

        draw_header()
        for row_idx, row in enumerate(rows):
            values = list(row[:len(headers)])
            values.extend(["-"] * (len(headers) - len(values)))
            wrapped = [
                self._wrap_text(value, width - 2 * pad_x, font_size)
                for value, width in zip(values, col_widths)
            ]
            row_h = max(8, max(len(lines) for lines in wrapped) * line_h + 2 * pad_y)

            if self.get_y() + row_h > bottom_limit:
                self.add_page()
                draw_header()

            y, x = self.get_y(), x0
            for idx, (width, lines) in enumerate(zip(col_widths, wrapped)):
                fill = BRAND_LIGHT_BG if row_idx % 2 else COLOR_WHITE
                self.set_fill_color(*fill)
                self.set_draw_color(*COLOR_BORDER)
                self.rect(x, y, width, row_h, "DF")
                self.set_font(fn, "", font_size)
                self.set_text_color(*COLOR_TEXT)
                self.set_xy(x + pad_x, y + pad_y)
                header_name = str(headers[idx])
                align = "C" if any(k in header_name for k in ("판정", "등급", "우선순위", "결과", "확인")) else "L"
                self.multi_cell(width - 2 * pad_x, line_h, "\n".join(lines), 0, align)
                x += width
            self.set_xy(x0, y + row_h)
        self.ln(2)

    def draw_visual_scorecard(self, scores_data):
        fn = self._fn()
        scores_data = scores_data if isinstance(scores_data, dict) else {}
        self.check_page_break(39)
        start_y = self.get_y()
        blocks = [
            ("관리자 선임", scores_data.get("manager_score")),
            ("방지시설 기준", scores_data.get("prevention_score")),
            ("LDAR 점검", scores_data.get("ldar_score")),
            ("기록 충실성", scores_data.get("record_score")),
        ]
        overall = scores_data.get("overall_score")
        overall = overall if isinstance(overall, dict) else {}
        gap, overall_w = 2.5, 45
        block_w = (CONTENT_W - 4 * gap - overall_w) / 4
        x = LEFT

        for title, item in blocks:
            item = item if isinstance(item, dict) else {}
            score = _as_float(item.get("score"))
            grade = _safe_text(item.get("grade"), "미산정")
            color = _grade_color(grade, score)
            self.set_fill_color(*COLOR_WHITE)
            self.set_draw_color(*COLOR_BORDER)
            self.rect(x, start_y, block_w, 29, "FD")
            self.set_fill_color(*color)
            self.rect(x, start_y, block_w, 2, "F")
            self.set_xy(x + 1.5, start_y + 4)
            self.set_font(fn, "", 7.3)
            self.set_text_color(*COLOR_MUTED)
            self.cell(block_w - 3, 5, title, 0, 0, "C")
            self.set_xy(x + 1, start_y + 10)
            self.set_font(fn, "B", 17)
            self.set_text_color(*BRAND_NAVY)
            self.cell(block_w - 2, 9, f"{score:g}" if score is not None else "-", 0, 0, "C")
            self.set_xy(x + 1, start_y + 20)
            self.set_font(fn, "B", 7.5)
            self.set_text_color(*color)
            self.cell(block_w - 2, 5, grade, 0, 0, "C")
            x += block_w + gap

        overall_score = _as_float(overall.get("score"))
        overall_grade = _safe_text(overall.get("grade"), "미산정")
        overall_color = _grade_color(overall_grade, overall_score)
        self.set_fill_color(*BRAND_LIGHT_BG)
        self.set_draw_color(*COLOR_BORDER)
        self.rect(x, start_y, overall_w, 29, "FD")
        self.set_fill_color(*overall_color)
        self.rect(x, start_y, overall_w, 2, "F")
        self.set_xy(x + 1, start_y + 3)
        self.set_font(fn, "", 7.5)
        self.set_text_color(*COLOR_MUTED)
        self.cell(overall_w - 2, 5, "종합 결과", 0, 0, "C")
        self.set_xy(x + 1, start_y + 8)
        self.set_font(fn, "B", 15)
        self.set_text_color(*overall_color)
        self.cell(overall_w - 2, 9, overall_grade, 0, 0, "C")
        self.set_xy(x + 1, start_y + 19)
        self.set_font(fn, "", 7.5)
        self.set_text_color(*BRAND_NAVY)
        label = f"총점 {overall_score:g}점" if overall_score is not None else "총점 미산정"
        self.cell(overall_w - 2, 5, label, 0, 0, "C")
        self.set_y(start_y + 33)
        self.set_font(fn, "", 7.5)
        self.set_text_color(*COLOR_MUTED)
        self.multi_cell(0, 4.5, "※ 자료 미확보 항목은 적합으로 간주하지 않으며, 추가 확인이 필요합니다.")
        self.ln(1)

    def draw_air_quality_infographic(self, station_name, air_data):
        fn = self._fn()
        air_data = air_data if isinstance(air_data, dict) else {}
        self.check_page_break(55)
        start_y = self.get_y()
        pm10, o3 = air_data.get("pm10Value", "-"), air_data.get("o3Value", "-")
        pm_status, pm_color, pm_ratio = get_aqi_status(pm10, "PM10")
        o3_status, o3_color, o3_ratio = get_aqi_status(o3, "O3")
        self.set_fill_color(245, 248, 252)
        self.set_draw_color(*COLOR_BORDER)
        self.rect(LEFT, start_y, CONTENT_W, 48, "DF")
        self.set_xy(LEFT + 5, start_y + 3)
        self.set_font(fn, "B", 9.5)
        self.set_text_color(*BRAND_NAVY)
        self.cell(CONTENT_W - 10, 6, f"지역 대기질 참고 정보 | 측정소: {_safe_text(station_name)}", 0, 1, "L")

        cards = [
            (LEFT + 5, "오존 (O3)", o3, "ppm", o3_status, o3_color, o3_ratio, "참고값 0.09"),
            (LEFT + 98, "미세먼지 (PM10)", pm10, "㎍/㎥", pm_status, pm_color, pm_ratio, "참고값 80"),
        ]
        for x, label, value, unit, status, color, ratio, reference in cards:
            y = start_y + 12
            self.set_fill_color(*COLOR_WHITE)
            self.set_draw_color(*COLOR_BORDER)
            self.rect(x, y, 87, 30, "DF")
            self.set_xy(x + 4, y + 3)
            self.set_font(fn, "B", 8.5)
            self.set_text_color(*COLOR_TEXT)
            self.cell(48, 5, label, 0, 0, "L")
            self.set_xy(x + 4, y + 10)
            self.set_font(fn, "B", 13)
            self.set_text_color(*BRAND_NAVY)
            self.cell(50, 7, f"{_safe_text(value)} {unit}", 0, 0, "L")
            self.set_fill_color(*color)
            self.rect(x + 61, y + 3, 21, 6, "F")
            self.set_xy(x + 61, y + 3.5)
            self.set_font(fn, "B", 7)
            self.set_text_color(*COLOR_WHITE)
            self.cell(21, 5, status, 0, 0, "C")
            bar_x, bar_y, bar_w = x + 4, y + 23, 75
            self.set_fill_color(230, 235, 240)
            self.rect(bar_x, bar_y, bar_w, 2.5, "F")
            self.set_fill_color(*color)
            self.rect(bar_x, bar_y, bar_w * ratio, 2.5, "F")
            self.set_xy(bar_x, y + 25.5)
            self.set_font(fn, "", 6.5)
            self.set_text_color(*COLOR_MUTED)
            self.cell(bar_w, 3, reference, 0, 0, "L")

        self.set_y(start_y + 51)
        self.set_font(fn, "", 7.5)
        self.set_text_color(*COLOR_MUTED)
        self.multi_cell(0, 4, "※ 지역 대기질은 참고 정보이며, 사업장 배출시설의 법적 준수 여부를 직접 판정하지 않습니다.")
        self.ln(1)

    def draw_text_box(self, text: str, title: str = ""):
        fn = self._fn()
        if title:
            self.check_page_break(15)
            self.set_font(fn, "B", 9.5)
            self.set_text_color(*BRAND_NAVY)
            self.cell(0, 7, title, 0, 1, "L")

        content = _safe_text(text, "")
        if not content or content == "-":
            self.set_fill_color(*BRAND_LIGHT_BG)
            self.set_font(fn, "", 8.5)
            self.set_text_color(*COLOR_MUTED)
            self.multi_cell(0, 6, "해당 내용이 입력되지 않았습니다. 관련 자료를 확인해 주세요.", 0, "L", True)
            self.ln(2)
            return

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                self.ln(2)
                continue
            if re.match(r"^【.*】$", line) or re.match(r"^\[.*\]$", line):
                self.check_page_break(12)
                self.ln(1)
                self.set_font(fn, "B", 9.5)
                self.set_text_color(*BRAND_NAVY)
                self.multi_cell(0, 6, line, 0, "L")
            elif re.match(r"^(?:\d+[.)]|[-•✓])\s*", line):
                self.check_page_break(10)
                self.set_font(fn, "", 8.7)
                self.set_text_color(*COLOR_TEXT)
                self.set_x(LEFT + 4)
                self.multi_cell(CONTENT_W - 4, 5.5, line, 0, "L")
            else:
                self.set_font(fn, "", 8.7)
                self.set_text_color(*COLOR_TEXT)
                self.set_x(LEFT)
                self.multi_cell(CONTENT_W, 5.5, line, 0, "L")
        self.ln(2)


def _get_rows(data, section, key="data"):
    value = data.get(section, {})
    if not isinstance(value, dict):
        return []
    rows = value.get(key, [])
    return rows if isinstance(rows, list) else []


def _record_value(record, key, default="-"):
    if not isinstance(record, dict):
        return default
    return _safe_text(record.get(key), default)


def create_gov_report_pdf(ai_data: dict, user_info: dict, air_advice: str, air_data: dict, station_name: str) -> bytes:
    """
    app.py의 기존 호출과 호환되는 PDF 생성 함수입니다.
    함수명과 매개변수는 변경하지 않았습니다.
    """
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
    pdf.draw_zebra_table(["구분", "측정일", "방지시설명", "결과", "기준", "판정"], prev_rows, [22, 25, 62, 25, 25, 26])

    pdf.draw_sub_header("2) 비산누출시설 LDAR 점검 실적")
    ldar_rows = [
        [_record_value(p, "year"), _record_value(p, "target_count"), _record_value(p, "leak_count"),
         _record_value(p, "leak_rate"), _record_value(p, "recheck_done"), _record_value(p, "result")]
        for p in _get_rows(data, "ldar")
    ]
    pdf.draw_zebra_table(
        ["점검 연도", "대상 개소", "누출 수", "누출률", "재측정·조치", "최종 판정"],
        ldar_rows, [25, 30, 25, 25, 45, 35]
    )

    pdf.draw_sub_header("3) 시설별 진단 결과 및 추가 확인사항")
    parsed_items = data.get("parsed_items", [])
    item_rows = []
    if isinstance(parsed_items, list):
        for item in parsed_items:
            if isinstance(item, dict):
                item_rows.append([
                    _record_value(item, "facility", _record_value(item, "item")),
                    _record_value(item, "result", _record_value(item, "status")),
                    _record_value(item, "risk"),
                    _record_value(item, "recommendation", _record_value(item, "action")),
                ])
    if item_rows:
        pdf.draw_zebra_table(["시설·항목", "확인 결과", "위험도", "권고 조치"], item_rows, [42, 38, 25, 80])
    else:
        pdf.draw_text_box("별도 시설별 항목 데이터가 추출되지 않았습니다. 원본 진단 결과의 항목별 내용을 검토해 주세요.")

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
    pdf.draw_zebra_table(["위험 항목", "발생 가능성", "영향도", "우선순위"], risk_rows, [58, 42, 40, 45])
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
    pdf.draw_zebra_table(["단계·기간", "주요 개선 조치", "기대 효과"], roadmap_rows, [30, 92, 63])

    pdf.draw_sub_header("2) AI 정밀 진단 종합 의견")
    pdf.draw_text_box(data.get("overall_opinion", "-"))

    pdf.draw_sub_header("3) 우선 개선 조치 요약")
    actions = data.get("priority_actions", [])
    action_rows = []
    if isinstance(actions, list):
        for item in actions:
            if isinstance(item, dict):
                action_rows.append([
                    _record_value(item, "priority"), _record_value(item, "action"),
                    _record_value(item, "deadline"), _record_value(item, "owner")
                ])
            elif isinstance(item, str):
                action_rows.append(["-", item, "-", "-"])
    pdf.draw_zebra_table(["우선순위", "조치사항", "권고 기한", "담당"], action_rows, [28, 88, 35, 34])

    # 사. 법령
    pdf.draw_section_header("사. 관련 규제 및 법령 참고사항")
    pdf.draw_sub_header("1) 법령 검토 목록")
    laws = data.get("law_references", [])
    law_rows = []
    if isinstance(laws, list):
        for item in laws:
            if isinstance(item, dict):
                law_rows.append([
                    _record_value(item, "law_name", _record_value(item, "name")),
                    _record_value(item, "article", _record_value(item, "provision")),
                    _record_value(item, "summary", _record_value(item, "description")),
                    _record_value(item, "checked_date"),
                ])
    pdf.draw_zebra_table(["법령명", "조문", "검토 내용", "확인일"], law_rows, [43, 27, 90, 25])
    pdf.draw_text_box(
        "※ 법령 목록이 입력되지 않은 경우 최신 법령 확인이 완료된 것으로 볼 수 없습니다. "
        "법령 조문과 처분 기준은 국가법령정보센터 및 관할 기관의 최신 안내를 확인한 후 사용하세요."
    )

    # 아. 변경신고 및 후속 조치
    pdf.draw_section_header("아. 변경신고 및 추진체계")
    pdf.draw_sub_header("1) 변경신고 검토 시 확인할 사항")
    pdf.draw_text_box(
        "비산배출시설 신고 사업장은 신고 내용에 변경이 발생한 경우 적용 법령에 따른 변경신고 대상 여부와 제출 기한을 확인해야 합니다.\n"
        "1. 사업장 명칭 또는 대표자 변경 여부\n"
        "2. 비산배출시설의 신설·증설·교체·폐쇄 여부\n"
        "3. 시설관리계획 또는 방지시설 구성 변경 여부\n"
        "4. 기존 신고서 기재사항의 변경 또는 정정 필요 여부\n"
        "5. 변경신고서 및 첨부 자료 제출 여부"
    )
    pdf.draw_sub_header("2) 후속 조치 관리표")
    followups = data.get("followup_actions", [])
    followup_rows = []
    if isinstance(followups, list):
        for item in followups:
            if isinstance(item, dict):
                followup_rows.append([
                    _record_value(item, "action"), _record_value(item, "owner"),
                    _record_value(item, "deadline"), _record_value(item, "status")
                ])
    pdf.draw_zebra_table(["후속 조치", "담당자", "목표 기한", "진행 상태"], followup_rows, [80, 35, 35, 35])

    # 자. 체크리스트
    pdf.draw_section_header("자. 사업장 자가점검표")
    pdf.draw_sub_header("1) 정기 점검 체크리스트")
    checklist = [
        ["□", "일일", "방지시설 가동 상태 및 이상 유무 확인"],
        ["□", "일일", "국소배기장치 및 송풍기 가동 여부 확인"],
        ["□", "주간", "차압계 등 계측기 수치와 설계 범위 확인"],
        ["□", "월간", "흡착제 상태 및 교체 필요성 검토"],
        ["□", "반기", "시설관리기준에 따른 정기 점검 자료 확인"],
        ["□", "반기", "LDAR 점검, 누출 수리 및 재측정 기록 확인"],
        ["□", "연간", "보고서 제출 의무와 제출 기한 확인"],
    ]
    pdf.draw_zebra_table(["확인", "주기", "점검 항목"], checklist, [20, 30, 135])

    pdf.draw_sub_header("2) 점검 결과 기록")
    pdf.draw_zebra_table(
        ["점검일", "점검 항목", "결과", "조치 내용", "확인자"],
        [["", "", "", "", ""] for _ in range(4)],
        [25, 55, 25, 55, 25]
    )
    pdf.ln(4)
    pdf.set_font(pdf._fn(), "", 7.5)
    pdf.set_text_color(*COLOR_MUTED)
    pdf.multi_cell(
        0, 4.5,
        "본 보고서는 사업장 자가진단과 환경관리 개선을 지원하기 위한 참고자료입니다. "
        "입력 자료의 정확성, 최신 법령 적용 여부 및 최종 행정 판단은 별도 확인이 필요합니다."
    )

    output = pdf.output(dest="S")
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)
