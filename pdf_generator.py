"""
비산배출시설 정밀 자가진단 보고서 PDF 생성 모듈
- 기존 create_gov_report_pdf(ai_data, user_info, air_advice, air_data, station_name) 인터페이스 유지
- A4 공공기관 보고서 스타일, 요약 대시보드, 자동 줄바꿈 표, 페이지 머리글/바닥글
- 점수/법령/대기질 데이터는 입력값을 우선 사용하며, 누락된 값은 임의로 정상 점수로 채우지 않음
"""
import os
import re
import urllib.request
from datetime import datetime
from typing import Any, Iterable

from fpdf import FPDF
from utils import (
    FONT_FILE_NAME, FONT_BOLD_NAME, BRAND_NAVY, BRAND_ACCENT,
    BRAND_LIGHT_BG, BRAND_HEADER_BG, SCORE_COLORS, get_env_office,
    get_limit_ppm
)

# ------------------------------
# 디자인 토큰
# ------------------------------
INK = (35, 47, 62)
MUTED = (104, 117, 134)
NAVY = tuple(BRAND_NAVY)
ACCENT = tuple(BRAND_ACCENT)
PALE = tuple(BRAND_LIGHT_BG)
HEADER_BG = tuple(BRAND_HEADER_BG)
WHITE = (255, 255, 255)
BORDER = (218, 226, 235)
ROW_ALT = (246, 249, 252)
TEAL = (22, 139, 130)
GREEN = (37, 142, 95)
AMBER = (208, 133, 38)
RED = (190, 63, 68)
GRAY = (135, 145, 157)
PAGE_W, PAGE_H = 210, 297
LEFT, RIGHT = 15, 195
CONTENT_W = RIGHT - LEFT


def ensure_korean_font():
    """Nanum Gothic 폰트가 없으면 다운로드를 시도한다. 실패 시 기존 폰트로 진행."""
    reg_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
    bold_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"
    try:
        if not os.path.exists(FONT_FILE_NAME):
            urllib.request.urlretrieve(reg_url, FONT_FILE_NAME)
        if not os.path.exists(FONT_BOLD_NAME):
            urllib.request.urlretrieve(bold_url, FONT_BOLD_NAME)
    except Exception as exc:
        print(f"한글 폰트 준비 실패: {exc}")


def _safe(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _number(value: Any):
    try:
        cleaned = str(value).replace(",", "").replace("%", "").strip()
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _score_color(score: Any):
    n = _number(score)
    if n is None:
        return GRAY
    if n >= 90:
        return GREEN
    if n >= 70:
        return TEAL
    if n >= 50:
        return AMBER
    return RED


def get_aqi_status(val, item_type):
    """참고용 대기질 표시. 국내 공식 예보 등급과 혼동되지 않도록 보고서에서 참고값임을 표기."""
    v = _number(val)
    if v is None:
        return "정보없음", GRAY, 0
    if item_type == "PM10":
        if v <= 30:
            return "좋음", (50, 150, 255), min(max(v / 150, 0), 1)
        if v <= 80:
            return "보통", GREEN, min(max(v / 150, 0), 1)
        if v <= 150:
            return "나쁨", AMBER, min(max(v / 150, 0), 1)
        return "매우나쁨", RED, 1
    if item_type == "O3":
        if v <= 0.030:
            return "좋음", (50, 150, 255), min(max(v / 0.150, 0), 1)
        if v <= 0.090:
            return "보통", GREEN, min(max(v / 0.150, 0), 1)
        if v <= 0.150:
            return "나쁨", AMBER, min(max(v / 0.150, 0), 1)
        return "매우나쁨", RED, 1
    return "측정불가", GRAY, 0


class ProfessionalPDF(FPDF):
    def __init__(self, toc_data=None):
        super().__init__(orientation="P", unit="mm", format="A4")
        self._toc = toc_data or []
        self._section = "진단 결과"
        self._font_ready = False
        self.set_margins(LEFT, 19, 15)
        self.set_auto_page_break(auto=True, margin=18)
        self.alias_nb_pages()

    def _fn(self):
        return "Nanum" if os.path.exists(FONT_FILE_NAME) else "Arial"

    def _reg_fonts(self):
        ensure_korean_font()
        if os.path.exists(FONT_FILE_NAME):
            try:
                self.add_font("Nanum", "", FONT_FILE_NAME)
                bold_src = FONT_BOLD_NAME if os.path.exists(FONT_BOLD_NAME) else FONT_FILE_NAME
                self.add_font("Nanum", "B", bold_src)
                self._font_ready = True
            except Exception as exc:
                print(f"폰트 등록 실패: {exc}")
        return self._fn()

    def header(self):
        # 표지와 목차에는 본문 머리글을 넣지 않는다.
        if self.page_no() <= 2:
            return
        fn = self._fn()
        self.set_fill_color(*NAVY)
        self.rect(0, 0, PAGE_W, 14, "F")
        self.set_xy(LEFT, 4)
        self.set_font(fn, "B", 8)
        self.set_text_color(*WHITE)
        self.cell(105, 5, "비산배출시설 정밀 자가진단 보고서", 0, 0, "L")
        self.set_font(fn, "", 7.5)
        self.set_text_color(211, 226, 241)
        self.cell(CONTENT_W - 105, 5, self._section, 0, 0, "R")
        self.set_y(19)

    def footer(self):
        if self.page_no() <= 2:
            return
        self.set_y(-13)
        self.set_draw_color(*BORDER)
        self.set_line_width(0.25)
        self.line(LEFT, self.get_y(), RIGHT, self.get_y())
        self.set_y(-11)
        self.set_font(self._fn(), "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(CONTENT_W / 2, 5, "환경관리 정밀 자가진단 · 참고용 결과보고서", 0, 0, "L")
        self.cell(CONTENT_W / 2, 5, f"{self.page_no() - 2} / {{nb}}", 0, 0, "R")

    def set_section(self, title):
        self._section = title

    def _text_width(self, text):
        try:
            return self.get_string_width(str(text))
        except Exception:
            return len(str(text)) * 2.2

    def _wrap(self, text, width):
        """폰트 폭을 기준으로 문자열을 줄 단위로 나눈다."""
        text = str(text).replace("\r", "")
        result = []
        for paragraph in text.split("\n"):
            if not paragraph:
                result.append("")
                continue
            words = paragraph.split(" ")
            line = ""
            for word in words:
                candidate = word if not line else line + " " + word
                if self._text_width(candidate) <= width - 2:
                    line = candidate
                    continue
                if line:
                    result.append(line)
                    line = ""
                # 공백이 없는 긴 문자열도 폭에 맞춰 분리
                if self._text_width(word) <= width - 2:
                    line = word
                else:
                    piece = ""
                    for char in word:
                        if piece and self._text_width(piece + char) > width - 2:
                            result.append(piece)
                            piece = char
                        else:
                            piece += char
                    line = piece
            result.append(line)
        return result or [""]

    def _cell_lines(self, text, width, font_size=8):
        self.set_font(self._fn(), "", font_size)
        return self._wrap(_safe(text), width)

    def check_space(self, height, title=None):
        if self.get_y() + height > PAGE_H - 19:
            self.add_page()
            if title:
                self._section = title

    def draw_cover(self, company, address, industry, permit_no, date_str):
        fn = self._fn()
        self.set_fill_color(243, 247, 252)
        self.rect(0, 0, PAGE_W, PAGE_H, "F")
        self.set_fill_color(*NAVY)
        self.rect(0, 0, PAGE_W, 74, "F")
        self.set_fill_color(*ACCENT)
        self.rect(0, 0, 7, PAGE_H, "F")
        self.set_xy(18, 16)
        self.set_font(fn, "B", 9)
        self.set_text_color(204, 224, 241)
        self.cell(0, 6, "ENVIRONMENTAL COMPLIANCE · SELF DIAGNOSIS", 0, 1, "L")
        self.set_xy(18, 31)
        self.set_font(fn, "B", 22)
        self.set_text_color(*WHITE)
        self.cell(0, 12, "비산배출시설", 0, 1, "L")
        self.set_x(18)
        self.cell(0, 12, "정밀 자가진단 보고서", 0, 1, "L")
        self.set_xy(19, 62)
        self.set_font(fn, "", 9)
        self.set_text_color(214, 229, 242)
        self.cell(0, 6, "HAPs 비산배출시설 환경관리 적합성 점검", 0, 1, "L")

        # 정보 카드
        card_y = 91
        self.set_fill_color(*WHITE)
        self.set_draw_color(222, 230, 239)
        self.set_line_width(0.35)
        self.rect(17, card_y, 176, 104, "FD")
        self.set_xy(25, card_y + 8)
        self.set_font(fn, "B", 11)
        self.set_text_color(*NAVY)
        self.cell(0, 7, "진단 대상 사업장 정보", 0, 1, "L")
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.7)
        self.line(25, card_y + 18, 185, card_y + 18)

        rows = [
            ("사업장명", company),
            ("소재지", address),
            ("업종", industry),
            ("허가·신고번호", permit_no),
            ("보고서 작성일", date_str),
        ]
        y = card_y + 24
        for i, (label, value) in enumerate(rows):
            if i % 2 == 0:
                self.set_fill_color(247, 250, 253)
                self.rect(24, y, 162, 12, "F")
            self.set_xy(27, y + 2)
            self.set_font(fn, "B", 8.5)
            self.set_text_color(*MUTED)
            self.cell(34, 7, label, 0, 0, "L")
            self.set_xy(63, y + 2)
            self.set_font(fn, "", 8.5)
            self.set_text_color(*INK)
            self.multi_cell(119, 7, _safe(value).replace("\n", " "))
            y += 12

        # 확인란
        self.set_xy(17, 211)
        self.set_fill_color(232, 241, 249)
        self.rect(17, 211, 176, 31, "F")
        labels = ["진단 담당자", "검토자", "사업장 확인"]
        for i, label in enumerate(labels):
            x = 20 + i * 58
            self.set_xy(x, 216)
            self.set_font(fn, "B", 8)
            self.set_text_color(*NAVY)
            self.cell(54, 5, label, 0, 1, "C")
            self.set_draw_color(177, 193, 210)
            self.line(x + 5, 234, x + 49, 234)

        self.set_fill_color(*ACCENT)
        self.rect(7, 259, 203, 7, "F")
        self.set_xy(17, 271)
        self.set_font(fn, "B", 8)
        self.set_text_color(*NAVY)
        self.cell(0, 5, "AI 기반 환경관리 지원자료 · 사업장 자체 점검 및 개선계획 수립용", 0, 1, "C")
        self.set_xy(17, 279)
        self.set_font(fn, "", 7)
        self.set_text_color(*MUTED)
        self.cell(0, 5, "※ 본 보고서는 입력자료 기반 참고 결과이며, 법적 적합성 및 처분 여부는 관계 법령과 담당 기관의 확인이 필요합니다.", 0, 1, "C")

    def draw_toc(self, toc_items):
        fn = self._fn()
        self.set_fill_color(246, 249, 253)
        self.rect(0, 0, PAGE_W, PAGE_H, "F")
        self.set_fill_color(*NAVY)
        self.rect(0, 0, PAGE_W, 29, "F")
        self.set_xy(LEFT, 8)
        self.set_font(fn, "B", 16)
        self.set_text_color(*WHITE)
        self.cell(0, 10, "목 차", 0, 1, "L")
        self.set_xy(LEFT, 20)
        self.set_font(fn, "", 8)
        self.set_text_color(210, 226, 241)
        self.cell(0, 5, "CONTENTS", 0, 1, "L")
        self.set_y(42)
        for title, page in toc_items:
            sub = str(title).startswith("  ")
            self.set_x(LEFT + (7 if sub else 0))
            self.set_font(fn, "" if sub else "B", 8.5 if sub else 10)
            self.set_text_color(*(MUTED if sub else NAVY))
            clean = str(title).strip()
            self.cell(145 - (7 if sub else 0), 9, clean, 0, 0, "L")
            self.set_text_color(*MUTED)
            self.cell(CONTENT_W - 145, 9, str(page), 0, 1, "R")
            self.set_draw_color(226, 232, 239)
            self.line(LEFT, self.get_y(), RIGHT, self.get_y())

    def draw_section_header(self, title, set_section=True):
        if set_section:
            self._section = title
        self.check_space(25, title)
        fn = self._fn()
        self.ln(3)
        y = self.get_y()
        self.set_fill_color(*ACCENT)
        self.rect(LEFT, y, 2.2, 10, "F")
        self.set_xy(LEFT + 6, y)
        self.set_font(fn, "B", 12)
        self.set_text_color(*NAVY)
        self.cell(CONTENT_W - 6, 10, title, 0, 1, "L")
        self.set_draw_color(*BORDER)
        self.set_line_width(0.3)
        self.line(LEFT, self.get_y() + 1, RIGHT, self.get_y() + 1)
        self.ln(5)

    def draw_sub_header(self, title):
        self.check_space(15)
        fn = self._fn()
        self.ln(2)
        self.set_font(fn, "B", 9.5)
        self.set_text_color(*TEAL)
        self.cell(0, 6, title, 0, 1, "L")
        self.ln(1)

    def draw_note(self, text, fill=(242, 247, 251), color=MUTED):
        fn = self._fn()
        lines = self._wrap(text, CONTENT_W - 12)
        h = max(10, len(lines) * 4.5 + 5)
        self.check_space(h)
        y = self.get_y()
        self.set_fill_color(*fill)
        self.rect(LEFT, y, CONTENT_W, h, "F")
        self.set_fill_color(*ACCENT)
        self.rect(LEFT, y, 1.5, h, "F")
        self.set_xy(LEFT + 5, y + 2)
        self.set_font(fn, "", 8)
        self.set_text_color(*color)
        self.multi_cell(CONTENT_W - 10, 4.5, text)
        self.set_y(y + h + 3)

    def draw_zebra_table(self, headers, rows, col_widths, alignments=None, font_size=7.8):
        """각 셀의 줄 수를 계산해 행 높이를 자동으로 조정하는 표."""
        fn = self._fn()
        if not headers:
            return
        if abs(sum(col_widths) - CONTENT_W) > 1.5:
            # 기존 호출 코드의 너비 합계를 최대한 보존하면서 페이지 너비에 맞춤
            total = sum(col_widths) or 1
            col_widths = [w * CONTENT_W / total for w in col_widths]
        alignments = alignments or ["L"] * len(headers)
        self.set_font(fn, "B", 7.7)
        header_lines = [self._wrap(h, col_widths[i] - 4) for i, h in enumerate(headers)]
        header_h = max(8, max(len(x) for x in header_lines) * 4 + 4)
        self.check_space(header_h + 8)
        x0, y0 = LEFT, self.get_y()
        x = x0
        self.set_fill_color(*NAVY)
        self.set_draw_color(255, 255, 255)
        for i, h in enumerate(headers):
            self.rect(x, y0, col_widths[i], header_h, "F")
            self.set_xy(x + 2, y0 + 2)
            self.set_font(fn, "B", 7.7)
            self.set_text_color(*WHITE)
            self.multi_cell(col_widths[i] - 4, 4, h, 0, "C")
            x += col_widths[i]
        self.set_y(y0 + header_h)

        if not rows:
            self.set_fill_color(*ROW_ALT)
            self.set_draw_color(*BORDER)
            self.rect(LEFT, self.get_y(), CONTENT_W, 12, "DF")
            self.set_xy(LEFT + 2, self.get_y() + 3)
            self.set_font(fn, "", 8)
            self.set_text_color(*MUTED)
            self.cell(CONTENT_W - 4, 6, "해당 항목의 입력 데이터가 없습니다.", 0, 0, "C")
            self.ln(12)
            self.ln(2)
            return

        for ridx, row in enumerate(rows):
            values = list(row)
            if len(values) < len(headers):
                values += ["-"] * (len(headers) - len(values))
            values = values[:len(headers)]
            lines = [self._wrap(_safe(values[i]), col_widths[i] - 4) for i in range(len(headers))]
            row_h = max(8, max(len(c) for c in lines) * 4.1 + 4)
            if self.get_y() + row_h > PAGE_H - 19:
                self.add_page()
                # 페이지가 바뀌어도 표 머리글을 반복
                y0 = self.get_y()
                x = LEFT
                for i, h in enumerate(headers):
                    self.set_fill_color(*NAVY)
                    self.rect(x, y0, col_widths[i], header_h, "F")
                    self.set_xy(x + 2, y0 + 2)
                    self.set_font(fn, "B", 7.7)
                    self.set_text_color(*WHITE)
                    self.multi_cell(col_widths[i] - 4, 4, h, 0, "C")
                    x += col_widths[i]
                self.set_y(y0 + header_h)
            y = self.get_y()
            self.set_fill_color(*(WHITE if ridx % 2 == 0 else ROW_ALT))
            self.set_draw_color(*BORDER)
            self.rect(LEFT, y, CONTENT_W, row_h, "DF")
            x = LEFT
            for i, val in enumerate(values):
                if i:
                    self.set_draw_color(*BORDER)
                    self.line(x, y, x, y + row_h)
                self.set_xy(x + 2, y + 2)
                self.set_font(fn, "", font_size)
                self.set_text_color(*INK)
                self.multi_cell(col_widths[i] - 4, 4.1, _safe(val), 0, alignments[i] if i < len(alignments) else "L")
                x += col_widths[i]
            self.set_y(y + row_h)
        self.ln(4)

    def draw_metric_card(self, x, y, w, h, label, value, sub="", color=TEAL):
        fn = self._fn()
        self.set_fill_color(*WHITE)
        self.set_draw_color(*BORDER)
        self.rect(x, y, w, h, "FD")
        self.set_fill_color(*color)
        self.rect(x, y, 1.8, h, "F")
        self.set_xy(x + 4, y + 3)
        self.set_font(fn, "B", 7.5)
        self.set_text_color(*MUTED)
        self.cell(w - 8, 5, label, 0, 1, "L")
        self.set_xy(x + 4, y + 10)
        self.set_font(fn, "B", 17)
        self.set_text_color(*color)
        self.cell(w - 8, 9, str(value), 0, 1, "L")
        if sub:
            self.set_xy(x + 4, y + h - 7)
            self.set_font(fn, "", 6.8)
            self.set_text_color(*MUTED)
            self.cell(w - 8, 4, str(sub)[:55], 0, 1, "L")

    def draw_visual_scorecard(self, scores_data: dict):
        fn = self._fn()
        score_items = [
            ("관리자 선임", "manager_score"),
            ("방지시설 기준", "prevention_score"),
            ("LDAR 점검", "ldar_score"),
            ("기록 충실성", "record_score"),
        ]
        overall = scores_data.get("overall_score", {}) if isinstance(scores_data, dict) else {}
        overall_score = overall.get("score") if isinstance(overall, dict) else None
        overall_grade = overall.get("grade") if isinstance(overall, dict) else None

        self.check_space(45)
        y = self.get_y()
        gap = 3
        card_w = (CONTENT_W - gap * 4) / 5
        for i, (label, key) in enumerate(score_items):
            item = scores_data.get(key, {}) if isinstance(scores_data, dict) else {}
            score = item.get("score") if isinstance(item, dict) else None
            grade = item.get("grade") if isinstance(item, dict) else None
            shown = f"{score}점" if score is not None else "미산정"
            color = _score_color(score)
            self.draw_metric_card(LEFT + i * (card_w + gap), y, card_w, 29, label, shown, f"등급 {grade}" if grade else "등급 정보 없음", color)
        x = LEFT + 4 * (card_w + gap)
        color = _score_color(overall_score)
        shown = f"{overall_score}점" if overall_score is not None else "미산정"
        self.draw_metric_card(x, y, card_w, 29, "종합 점수", shown, f"종합등급 {overall_grade}" if overall_grade else "등급 정보 없음", color)
        self.set_y(y + 34)
        if overall_score is None:
            self.draw_note("종합 점수 정보가 제공되지 않아 점수 및 등급을 산정하지 않았습니다. 원자료와 평가 기준을 확인해 주세요.")

    def draw_air_quality_infographic(self, station_name: str, air_data: dict):
        fn = self._fn()
        self.check_space(43)
        pm10 = air_data.get("pm10Value", "-") if isinstance(air_data, dict) else "-"
        o3 = air_data.get("o3Value", "-") if isinstance(air_data, dict) else "-"
        pm10_stat, pm10_color, pm10_ratio = get_aqi_status(pm10, "PM10")
        o3_stat, o3_color, o3_ratio = get_aqi_status(o3, "O3")
        y = self.get_y()
        self.set_fill_color(243, 247, 251)
        self.rect(LEFT, y, CONTENT_W, 39, "F")
        self.set_xy(LEFT + 4, y + 3)
        self.set_font(fn, "B", 9)
        self.set_text_color(*NAVY)
        self.cell(CONTENT_W - 8, 5, f"관할 측정소: {_safe(station_name)}", 0, 1, "L")
        cards = [
            (LEFT + 4, "오존(O₃)", o3, "ppm", o3_stat, o3_color, o3_ratio),
            (LEFT + 92, "미세먼지(PM10)", pm10, "㎍/㎥", pm10_stat, pm10_color, pm10_ratio),
        ]
        for x, label, val, unit, status, color, ratio in cards:
            self.set_fill_color(*WHITE)
            self.set_draw_color(*BORDER)
            self.rect(x, y + 11, 83, 23, "FD")
            self.set_xy(x + 3, y + 13)
            self.set_font(fn, "B", 7.5)
            self.set_text_color(*MUTED)
            self.cell(43, 4, label, 0, 0, "L")
            self.set_font(fn, "B", 8)
            self.set_text_color(*color)
            self.cell(32, 4, status, 0, 1, "R")
            self.set_xy(x + 3, y + 19)
            self.set_font(fn, "B", 11)
            self.set_text_color(*INK)
            self.cell(77, 6, f"{_safe(val)} {unit}", 0, 1, "L")
            self.set_fill_color(228, 234, 241)
            self.rect(x + 3, y + 28, 76, 2, "F")
            self.set_fill_color(*color)
            self.rect(x + 3, y + 28, 76 * ratio, 2, "F")
        self.set_y(y + 42)
        self.draw_note("지역 대기질은 참고용 환경정보이며, 사업장 배출시설의 법적 적합성 판정 또는 배출농도 측정값을 의미하지 않습니다.")

    def draw_text_box(self, text: str, title: str = ""):
        fn = self._fn()
        if not text or not str(text).strip() or str(text).strip() == "-":
            self.draw_note("입력된 의견 또는 설명 데이터가 없습니다.")
            return
        if title:
            self.draw_sub_header(title)
        for raw in str(text).splitlines():
            line = raw.strip()
            if not line:
                self.ln(2)
                continue
            if re.match(r"^(【.*】|#{1,3}\s|[■◆●▶])", line):
                self.check_space(12)
                self.set_font(fn, "B", 9)
                self.set_text_color(*NAVY)
                self.set_x(LEFT)
                self.multi_cell(CONTENT_W, 5.5, line.lstrip("# "))
                self.ln(1)
            else:
                self.set_font(fn, "", 8.5)
                self.set_text_color(*INK)
                self.set_x(LEFT + 2)
                self.multi_cell(CONTENT_W - 2, 5, line)
        self.ln(2)

    def draw_checklist(self, checklist):
        rows = []
        for item in checklist:
            rows.append(["□", item[0], item[1], ""])
        self.draw_zebra_table(["확인", "주기", "점검 항목", "점검일/비고"], rows, [13, 24, 103, 40], font_size=7.6)


def _get_dict(data, key):
    value = data.get(key, {}) if isinstance(data, dict) else {}
    return value if isinstance(value, dict) else {}


def _get_list(data, key):
    value = data.get(key, []) if isinstance(data, dict) else []
    return value if isinstance(value, list) else []


def create_gov_report_pdf(ai_data: dict, user_info: dict, air_advice: str,
                          air_data: dict, station_name: str) -> bytes:
    """
    기존 app.py 호출 호환 함수.
    ai_data의 parsed 아래 scores/prevention/ldar/risk_matrix/roadmap 등을 사용한다.
    """
    now = datetime.now()
    date_str = now.strftime("%Y년 %m월 %d일")
    data = _get_dict(ai_data, "parsed")
    scores = _get_dict(data, "scores")
    user_info = user_info if isinstance(user_info, dict) else {}
    air_data = air_data if isinstance(air_data, dict) else {}

    toc_items = [
        ("가. 진단 결과 요약", "3"),
        ("나. 사업장 및 진단 개요", "4"),
        ("다. 준수율 종합 스코어카드", "4"),
        ("라. 지역 대기환경 참고정보", "5"),
        ("마. 시설별 정밀 진단 내역", "6"),
        ("바. 위험도 평가 및 우선 조치사항", "7"),
        ("사. 개선 로드맵 및 종합 의견", "8"),
        ("아. 관련 법령·행정처분 참고사항", "9"),
        ("자. 변경신고 안내 및 자가 체크리스트", "10"),
    ]

    pdf = ProfessionalPDF(toc_data=toc_items)
    pdf._reg_fonts()

    # 1. 표지
    pdf.add_page()
    pdf.draw_cover(
        user_info.get("name", "-"),
        user_info.get("addr", "-"),
        user_info.get("industry", "-"),
        user_info.get("permit_no", "-"),
        date_str,
    )

    # 2. 목차
    pdf.add_page()
    pdf.draw_toc(toc_items)

    # 3. 진단 결과 요약
    pdf.add_page()
    pdf.set_section("진단 결과 요약")
    pdf.draw_section_header("가. 진단 결과 요약")
    pdf.draw_note("본 요약은 제공된 사업장 자료와 AI 분석 결과를 정리한 참고자료입니다. 최종 법적 판단은 원자료 및 관계 법령을 확인하여야 합니다.")
    pdf.draw_sub_header("1) 종합 평가")
    pdf.draw_visual_scorecard(scores)

    overview = _safe(data.get("overall_opinion", "-"))
    pdf.draw_sub_header("2) 핵심 진단 의견")
    pdf.draw_text_box(overview)

    risk_list = _get_list(data, "risk_matrix")
    if risk_list:
        pdf.draw_sub_header("3) 우선 확인이 필요한 위험 항목")
        top_risks = []
        for item in risk_list[:5]:
            if isinstance(item, dict):
                top_risks.append([
                    item.get("item", "-"),
                    item.get("probability", "-"),
                    item.get("impact", "-"),
                    item.get("priority", "-"),
                ])
        pdf.draw_zebra_table(["위험 항목", "발생 가능성", "영향도", "우선순위"], top_risks, [65, 35, 35, 45])
    else:
        pdf.draw_note("위험도 평가 데이터가 제공되지 않았습니다. 위험도는 임의로 생성하지 않았습니다.")

    # 4. 사업장 개요
    pdf.add_page()
    pdf.set_section("사업장 및 진단 개요")
    pdf.draw_section_header("나. 사업장 및 진단 개요")
    pdf.draw_sub_header("1) 사업장 기본 정보")
    pdf.draw_zebra_table(
        ["항목", "내용", "항목", "내용"],
        [
            ["사업장명", user_info.get("name", "-"), "소재지", user_info.get("addr", "-")],
            ["업종", user_info.get("industry", "-"), "허가·신고번호", user_info.get("permit_no", "-")],
            ["진단일자", date_str, "관할 측정소", station_name or "-"],
        ],
        [27, 63, 30, 60],
    )
    pdf.draw_sub_header("2) 진단자료 및 해석 유의사항")
    pdf.draw_note("분석 결과는 업로드된 자료의 내용과 추출 품질에 영향을 받을 수 있습니다. 원본 신고증명서, 측정기록, 점검기록과 대조하여 누락·오인식 여부를 확인해 주세요.")

    # 점수 페이지(요약과 중복되는 상세 평가)
    pdf.set_section("준수율 종합 스코어카드")
    pdf.draw_section_header("다. 준수율 종합 스코어카드")
    pdf.draw_visual_scorecard(scores)
    score_rows = []
    for label, key in [
        ("관리자 선임", "manager_score"),
        ("방지시설 기준", "prevention_score"),
        ("LDAR 점검", "ldar_score"),
        ("기록 충실성", "record_score"),
        ("종합 점수", "overall_score"),
    ]:
        item = _get_dict(scores, key)
        score_rows.append([label, item.get("score", "미산정"), item.get("grade", "정보 없음"), item.get("comment", item.get("description", "-"))])
    pdf.draw_zebra_table(["평가 영역", "점수", "등급", "비고"], score_rows, [37, 25, 25, 93])
    pdf.draw_note("점수의 산정 기준과 가중치는 시스템에서 사용한 평가 로직을 확인해야 합니다. 원자료가 없는 항목은 미산정으로 표시합니다.")

    # 지역 대기환경
    pdf.add_page()
    pdf.set_section("지역 대기환경 참고정보")
    pdf.draw_section_header("라. 지역 대기환경 참고정보")
    pdf.draw_air_quality_infographic(station_name, air_data)
    pdf.draw_sub_header("1) 대기환경 및 VOCs 관리 참고 의견")
    pdf.draw_text_box(air_advice or "제공된 전문가 제언 데이터가 없습니다.")

    # 시설별 상세
    pdf.add_page()
    pdf.set_section("시설별 정밀 진단 내역")
    pdf.draw_section_header("마. 시설별 정밀 진단 내역")
    pdf.draw_sub_header("1) 방지시설 배출농도 추이(THC)")
    prevention = _get_dict(data, "prevention")
    prev_rows = []
    for item in _get_list(prevention, "data"):
        if isinstance(item, dict):
            prev_rows.append([
                item.get("period", "-"), item.get("date", "-"),
                item.get("facility", "-"), item.get("value", "-"),
                item.get("limit", "-"), item.get("result", "-"),
            ])
    pdf.draw_zebra_table(["구분", "측정일", "방지시설명", "결과", "기준", "판정"], prev_rows, [22, 25, 53, 25, 25, 30])

    pdf.draw_sub_header("2) 비산누출시설 LDAR 점검 실적")
    ldar = _get_dict(data, "ldar")
    ldar_rows = []
    for item in _get_list(ldar, "data"):
        if isinstance(item, dict):
            ldar_rows.append([
                item.get("year", "-"), item.get("target_count", "-"),
                item.get("leak_count", "-"), item.get("leak_rate", "-"),
                item.get("recheck_done", "-"), item.get("result", "-"),
            ])
    pdf.draw_zebra_table(["점검 연도", "대상 개소", "누출 수", "누출률", "재측정·조치", "최종 판정"], ldar_rows, [25, 30, 25, 25, 42, 33])

    # 위험도
    pdf.add_page()
    pdf.set_section("위험도 평가 및 우선 조치사항")
    pdf.draw_section_header("바. 위험도 평가 및 우선 조치사항")
    pdf.draw_sub_header("1) 위험도 평가 매트릭스")
    risk_rows = []
    for item in _get_list(data, "risk_matrix"):
        if isinstance(item, dict):
            risk_rows.append([
                item.get("item", "-"), item.get("probability", "-"),
                item.get("impact", "-"), item.get("priority", "-"),
            ])
    pdf.draw_zebra_table(["위험 항목", "발생 가능성", "영향도", "우선순위"], risk_rows, [65, 35, 35, 45])
    pdf.draw_sub_header("2) 관리상 우선 확인사항")
    pdf.draw_note("우선순위가 높게 표시된 항목부터 증빙자료와 현장 상태를 확인하고, 필요 시 담당자 검토 및 시정조치를 진행하세요. 표에 표시된 우선순위는 제공된 AI 분석값을 기준으로 합니다.")

    # 로드맵 / 의견
    pdf.add_page()
    pdf.set_section("개선 로드맵 및 종합 의견")
    pdf.draw_section_header("사. 개선 로드맵 및 종합 의견")
    pdf.draw_sub_header("1) 단계별 개선 로드맵")
    roadmap_rows = []
    for item in _get_list(data, "improvement_roadmap"):
        if isinstance(item, dict):
            roadmap_rows.append([
                item.get("phase", "-"),
                item.get("action", "-"),
                item.get("expected_effect", "-"),
            ])
    pdf.draw_zebra_table(["단계·기간", "주요 개선 조치", "기대 효과"], roadmap_rows, [30, 85, 65])
    pdf.draw_sub_header("2) AI 정밀 진단 종합 의견")
    pdf.draw_text_box(data.get("overall_opinion", "-"))
    pdf.draw_sub_header("3) 후속 관리 권고")
    pdf.draw_note("개선 조치별 담당자, 완료 목표일, 증빙자료, 완료 여부를 별도 관리대장에 기록하면 후속 점검과 내부 보고에 활용하기 좋습니다.")

    # 법령 참고사항
    pdf.add_page()
    pdf.set_section("관련 법령·행정처분 참고사항")
    pdf.draw_section_header("아. 관련 법령·행정처분 참고사항")
    pdf.draw_note("아래 표는 원본 코드에 제공된 참고 문구를 정리한 것으로, 법령 개정·위반 유형·위반 횟수·관할기관 판단에 따라 적용이 달라질 수 있습니다. 대외 배포 전 최신 법령 원문과 대조해 주세요.", fill=(255, 247, 235), color=(135, 86, 32))
    pdf.draw_sub_header("1) 벌칙 및 과태료 참고")
    law1 = [
        ["시설개선 조치명령 미이행", "5년 이하 징역 또는 5천만원 이하 벌금(원본 기재 내용)"],
        ["비산배출시설 미신고 설치·운영", "300만원 이하 벌금(원본 기재 내용)"],
        ["정기점검 미수검", "300만원 이하 과태료(원본 기재 내용)"],
        ["변경신고 미이행", "200만원 이하 과태료(원본 기재 내용)"],
    ]
    pdf.draw_zebra_table(["위반 대상", "벌칙·과태료 참고 내용"], law1, [65, 115])
    pdf.draw_sub_header("2) 위반 횟수별 행정처분 참고표")
    law2 = [
        ["신고·변경신고 미이행", "경고", "경고", "조업정지 10일", "조업정지 20일"],
        ["시설관리기준 미준수", "경고", "조업정지 10일", "조업정지 20일", "조업정지 20일"],
        ["정기점검 미수검", "경고", "경고", "조업정지 10일", "조업정지 20일"],
        ["조치명령 미이행", "조업정지 10일", "조업정지 20일", "조업정지 30일", "조업정지 30일"],
    ]
    pdf.draw_zebra_table(["위반 사항", "1차", "2차", "3차", "4차"], law2, [52, 32, 32, 32, 32])

    # 변경신고 + 체크리스트
    pdf.add_page()
    pdf.set_section("변경신고 안내 및 자가 체크리스트")
    pdf.draw_section_header("자. 변경신고 안내 및 자가 체크리스트")
    pdf.draw_sub_header("1) 변경신고 여부 확인이 필요한 상황")
    pdf.draw_text_box(
        "※ 다음은 변경신고 필요 여부를 검토하기 위한 일반적인 확인 항목입니다. 실제 신고 요건과 기한은 최신 관계 법령 및 관할기관 안내를 확인하세요.\n"
        "1. 사업장 명칭 또는 대표자 변경\n"
        "2. 비산배출시설 또는 관리계획 변경\n"
        "3. 시설 임대, 증설, 교체 또는 일부 폐쇄\n"
        "4. 신고서 기재사항의 오기·누락 정정\n"
        "5. 비산배출시설의 전부 폐쇄"
    )
    pdf.draw_sub_header("2) 일상·정기 점검 체크리스트")
    checklist = [
        ["일일", "방지시설 가동 상태 확인 및 이상 유무 기록"],
        ["일일", "국소배기장치 팬 가동 여부와 외관 확인"],
        ["주간", "차압계 수치 기록 및 관리 범위 이탈 여부 확인"],
        ["월간", "흡착제 상태·교체주기 확인 및 교체 계획 수립"],
        ["반기", "방지시설 처리효율 및 측정 결과 기록 확인"],
        ["반기", "LDAR 점검, 누출 수리 및 재측정 결과 기록 확인"],
        ["연간", "정기점검보고서 제출 대상·기한·제출처 확인"],
    ]
    checklist_rows = [["□", period, task, ""] for period, task in checklist]
    pdf.draw_zebra_table(["확인", "주기", "점검 항목", "점검일·비고"], checklist_rows, [13, 24, 103, 40])
    pdf.draw_note("이 체크리스트는 내부 점검 보조용입니다. 법정 점검 주기·보고 기한은 시설 유형과 적용 법령에 따라 달라질 수 있으므로 반드시 최신 기준을 확인하세요.")

    # PDF 바이트 반환. FPDF2의 output() 반환형이 bytearray/str인 경우를 모두 처리.
    output = pdf.output(dest="S")
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)
