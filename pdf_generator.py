import os
from fpdf import FPDF
from datetime import datetime
import re
from utils import FONT_FILE_NAME, FONT_BOLD_NAME, BRAND_NAVY, BRAND_ACCENT, BRAND_LIGHT_BG, BRAND_HEADER_BG, SCORE_COLORS, get_env_office, get_limit_ppm

class ProfessionalPDF(FPDF):
    def __init__(self, toc_data=None):
        super().__init__()
        self._toc = toc_data or []
        self._section = ""
        self.page_break_trigger = 265 

    def _fn(self) -> str:
        return "Nanum" if os.path.exists(FONT_FILE_NAME) else "Arial"

    def _reg_fonts(self):
        if os.path.exists(FONT_FILE_NAME):
            self.add_font("Nanum", "", FONT_FILE_NAME)
            bold_src = FONT_BOLD_NAME if os.path.exists(FONT_BOLD_NAME) else FONT_FILE_NAME
            self.add_font("Nanum", "B", bold_src)
        return self._fn()

    def check_page_break(self, required_height):
        if self.get_y() + required_height > self.page_break_trigger:
            self.add_page()

    def header(self):
        if self.page_no() <= 2: return
        fn = self._fn()
        self.set_font(fn, "B", 8); self.set_text_color(*BRAND_NAVY); self.set_y(7)
        self.cell(95, 5, "비산배출시설 정밀 자가진단 보고서", 0, 0, "L")
        self.cell(95, 5, self._section, 0, 0, "R")
        self.set_draw_color(*BRAND_ACCENT); self.set_line_width(0.3); self.line(10, 13, 200, 13)

    def footer(self):
        if self.page_no() <= 2: return
        self.set_y(-13); fn = self._fn()
        self.set_font(fn, "", 8); self.set_text_color(150, 155, 165); self.set_draw_color(210, 215, 225); self.set_line_width(0.25)
        self.line(10, self.get_y(), 200, self.get_y()); self.ln(1); self.cell(0, 4, f"- {self.page_no() - 2} -", 0, 0, "C")

    def draw_cover(self, company, address, industry, permit_no, date_str):
        fn = self._fn()
        self.set_fill_color(*BRAND_LIGHT_BG); self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*BRAND_NAVY); self.rect(0, 0, 210, 26, "F")
        self.set_y(8); self.set_font(fn, "B", 10); self.set_text_color(220, 232, 248); self.cell(0, 8, "한국환경공단 비산배출 자가진단 시스템 (시범사업)  |  v105.1 Modular", 0, 1, "C")
        self.set_fill_color(*BRAND_ACCENT); self.rect(0, 26, 7, 271, "F")
        self.set_fill_color(255, 255, 255); self.set_draw_color(195, 212, 235); self.set_line_width(0.5); self.rect(16, 38, 178, 198, "FD")
        self.set_fill_color(*BRAND_ACCENT); self.rect(16, 38, 178, 15, "F")
        self.set_y(41); self.set_font(fn, "B", 14); self.set_text_color(255, 255, 255); self.cell(0, 9, "비산배출시설 정밀 자가진단 보고서", 0, 1, "C")
        info_y = 69; row_h = 12
        info_rows = [("진단 대상 사업장", company), ("소      재      지", address), ("업   종   분   류", industry), ("보   고   일   자", date_str)]
        for i, (k, v) in enumerate(info_rows):
            self.set_fill_color(*(BRAND_LIGHT_BG if i % 2 == 0 else (255, 255, 255)))
            self.set_xy(20, info_y + i * row_h); self.set_font(fn, "B", 9); self.set_text_color(*BRAND_NAVY); self.cell(50, row_h - 1, k, 0, 0, "R", fill=True)
            self.set_font(fn, "", 9); self.set_text_color(30, 40, 60); self.cell(130, row_h - 1, " " + str(v), 0, 0, "L", fill=True)
        self.set_fill_color(*BRAND_ACCENT); self.rect(0, 248, 210, 8, "F")

    def draw_toc(self, toc_items):
        fn = self._fn(); self.set_fill_color(*BRAND_LIGHT_BG); self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*BRAND_NAVY); self.rect(0, 0, 210, 20, "F")
        self.set_y(5); self.set_font(fn, "B", 12); self.set_text_color(220, 232, 248); self.cell(0, 10, "목    차  (Table of Contents)", 0, 1, "C"); self.ln(4)
        for title, page in toc_items:
            is_sub = title.startswith("  "); self.set_x(22 if is_sub else 15); self.set_font(fn, "" if is_sub else "B", 9 if is_sub else 11); self.set_text_color(*(80, 95, 115) if is_sub else BRAND_NAVY)
            self.cell(150, 7, title.strip()); self.cell(20, 7, page, 0, 1, "R")

    def draw_section_header(self, txt, set_section=True):
        fn = self._fn(); self.check_page_break(25); self.ln(2)
        if set_section: self._section = txt
        self.set_fill_color(*BRAND_ACCENT); self.rect(10, self.get_y(), 4, 11, "F")
        self.set_font(fn, "B", 13); self.set_text_color(*BRAND_NAVY); self.set_x(16); self.cell(0, 11, txt, 0, 1, "L")
        self.set_draw_color(*BRAND_ACCENT); self.set_line_width(0.4); self.line(10, self.get_y(), 200, self.get_y()); self.ln(2)

    def draw_zebra_table(self, headers, rows, col_widths, highlight_last_col=False):
        fn = self._fn(); self.set_fill_color(*BRAND_HEADER_BG); self.set_draw_color(175, 195, 220); self.set_line_width(0.2); self.set_font(fn, "B", 9); self.set_text_color(*BRAND_NAVY)
        for i, h in enumerate(headers): self.cell(col_widths[i], 8, h, border="TB", align="C", fill=True)
        self.ln(); self.set_font(fn, "", 8.5); self.set_text_color(35, 45, 60); alt = False
        for row in rows:
            self.check_page_break(8); self.set_fill_color(*(BRAND_LIGHT_BG if alt else (255, 255, 255)))
            for i, val in enumerate(row): self.cell(col_widths[i], 7, str(val), border="B", align="C", fill=True)
            self.ln(); alt = not alt

    def draw_scorecard(self, scores_data: dict):
        fn = self._fn(); self.check_page_break(40); start_y = self.get_y()
        self.set_fill_color(250, 251, 254); self.set_draw_color(210, 220, 238); self.set_line_width(0.35); self.rect(10, start_y, 190, 32, "FD")
        self.set_xy(15, start_y + 4); self.set_font(fn, "B", 10); self.set_text_color(*BRAND_NAVY); self.cell(0, 6, "항목별 진단 결과 요약")
        grade = scores_data.get("overall_score", {}).get("grade", "F")
        self.set_font(fn, "B", 24); self.set_text_color(*SCORE_COLORS.get(grade, (100,100,100))); self.set_xy(160, start_y + 8); self.cell(30, 15, grade, 0, 0, "C")

    def draw_text_box(self, text: str, title: str = ""):
        fn = self._fn(); w = 185; self.check_page_break(25)
        if title: self.set_font(fn, "B", 10); self.set_text_color(*BRAND_NAVY); self.cell(0, 8, title, 0, 1, "L")
        for line in text.split("\n"):
            line = line.strip()
            if not line: continue
            if re.match(r"^【.*】", line):
                self.check_page_break(15); self.ln(3); self.set_font(fn, "B", 10); self.set_text_color(*BRAND_NAVY)
                self.multi_cell(w, 6, line); self.set_font(fn, "", 9.5); self.set_text_color(50, 50, 50)
            else:
                self.multi_cell(w, 6, "  " + line)

def create_gov_report_pdf(ai_data: dict, user_info: dict, air_advice: str, air_data: dict, station_name: str) -> bytes:
    now_str = datetime.now().strftime("%Y년 %m월 %d일"); data = ai_data.get("parsed", {}); scores = data.get("scores", {})
    toc_items = [("가. 사업장 및 진단 개요", "1"), ("나. 준수율 종합 스코어카드", "1"), ("다. 지역 환경 분석", "2"), ("라. 시설별 정밀 진단 내역", "3"), ("바. AI 정밀 진단 종합 의견", "4")]
    pdf = ProfessionalPDF(toc_data=toc_items); pdf._reg_fonts(); pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page(); pdf.draw_cover(user_info.get("name", "-"), user_info.get("addr", "-"), user_info.get("industry", "-"), "-", now_str)
    pdf.add_page(); pdf.draw_toc(toc_items)
    pdf.add_page(); pdf.draw_section_header("가. 사업장 및 진단 개요")
    pdf.draw_zebra_table(["항목", "내용", "항목", "내용"], [["사업장명", user_info.get("name", "-"), "소재지", user_info.get("addr", "-")], ["업종분류", user_info.get("industry", "-"), "진단일자", now_str]], [32, 63, 32, 63])
    pdf.draw_section_header("나. 준수율 종합 스코어카드"); pdf.draw_scorecard(scores)
    pdf.add_page(); pdf.draw_section_header("다. 지역 환경 분석"); pdf.draw_text_box(air_advice, title=f"관할 측정소: {station_name}")
    pdf.add_page(); pdf.draw_section_header("라. 시설별 정밀 진단 내역")
    prev_rows = [[p.get("period","-"), p.get("date","-"), p.get("facility","-"), p.get("value","-"), p.get("limit","-"), p.get("result","-")] for p in data.get("prevention", {}).get("data", [])]
    pdf.draw_zebra_table(["구분", "측정일", "시설명", "결과", "기준", "판정"], prev_rows, [25, 25, 60, 25, 25, 30])
    pdf.add_page(); pdf.draw_section_header("바. AI 정밀 진단 종합 의견"); pdf.draw_text_box(data.get("overall_opinion", "-"))
    return bytes(pdf.output())
