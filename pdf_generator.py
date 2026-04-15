import os
from fpdf import FPDF
from datetime import datetime
import re
from utils import FONT_FILE_NAME, FONT_BOLD_NAME, BRAND_NAVY, BRAND_ACCENT, BRAND_LIGHT_BG, BRAND_HEADER_BG, SCORE_COLORS, get_env_office, get_limit_ppm

class ProfessionalPDF(FPDF):
    def __init__(self, toc_data=None):
        super().__init__()
        self._toc      = toc_data or []
        self._section = ""
        self.page_break_trigger = 265 

    def _fn(self) -> str:
        return "Nanum" if os.path.exists(FONT_FILE_NAME) else "Arial"

    def _reg_fonts(self):
        if os.path.exists(FONT_FILE_NAME):
            self.add_font("Nanum", "",  FONT_FILE_NAME)
            bold_src = FONT_BOLD_NAME if os.path.exists(FONT_BOLD_NAME) else FONT_FILE_NAME
            self.add_font("Nanum", "B", bold_src)
        return self._fn()

    def check_page_break(self, required_height):
        if self.get_y() + required_height > self.page_break_trigger:
            self.add_page()

    def header(self):
        if self.page_no() <= 2: return
        fn = self._fn()
        self.set_font(fn, "B", 8)
        self.set_text_color(*BRAND_NAVY)
        self.set_y(7)
        self.cell(95, 5, "비산배출시설 정밀 자가진단 보고서", 0, 0, "L")
        self.cell(95, 5, self._section, 0, 0, "R")
        self.set_draw_color(*BRAND_ACCENT)
        self.set_line_width(0.3)
        self.line(10, 13, 200, 13)

    def footer(self):
        if self.page_no() <= 2: return
        self.set_y(-13)
        fn = self._fn()
        self.set_font(fn, "", 8)
        self.set_text_color(150, 155, 165)
        self.set_draw_color(210, 215, 225)
        self.set_line_width(0.25)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(1)
        self.cell(0, 4, f"- {self.page_no() - 2} -", 0, 0, "C")

    def draw_cover(self, company, address, industry, permit_no, date_str):
        fn = self._fn()
        self.set_fill_color(*BRAND_LIGHT_BG); self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*BRAND_NAVY); self.rect(0, 0, 210, 26, "F")
        self.set_y(8); self.set_font(fn, "B", 10); self.set_text_color(220, 232, 248)
        self.cell(0, 8, "한국환경공단 비산배출 자가진단 시스템 (시범사업)  |  v105.1 Modular", 0, 1, "C")
        self.set_fill_color(*BRAND_ACCENT); self.rect(0, 26, 7, 271, "F")
        self.set_fill_color(255, 255, 255); self.set_draw_color(195, 212, 235); self.set_line_width(0.5)
        self.rect(16, 38, 178, 198, "FD")
        self.set_fill_color(*BRAND_ACCENT); self.rect(16, 38, 178, 15, "F")
        self.set_y(41); self.set_font(fn, "B", 14); self.set_text_color(255, 255, 255)
        self.cell(0, 9, "비산배출시설 정밀 자가진단 보고서", 0, 1, "C")
        self.set_y(56); self.set_font(fn, "B", 9); self.set_text_color(*BRAND_NAVY)
        self.cell(0, 6, "HAPs 비산배출시설 환경관리 적합성 정밀 진단", 0, 1, "C")
        self.set_draw_color(*BRAND_ACCENT); self.set_line_width(0.35); self.line(24, 64, 194, 64)
        info_y = 69; row_h = 12
        info_rows = [("진단 대상 사업장", company), ("소      재      지", address), ("업   종   분   류", industry), ("허 가 신 고 번 호", permit_no), ("보   고   일   자", date_str)]
        for i, (k, v) in enumerate(info_rows):
            self.set_fill_color(*(BRAND_LIGHT_BG if i % 2 == 0 else (255, 255, 255)))
            self.set_xy(20, info_y + i * row_h); self.set_font(fn, "B", 9); self.set_text_color(*BRAND_NAVY)
            self.cell(50, row_h - 1, k, 0, 0, "R", fill=True); self.set_font(fn, "", 9); self.set_text_color(30, 40, 60)
            self.cell(130, row_h - 1, " " + v.replace('\n', ' '), 0, 0, "L", fill=True)
        sign_y = info_y + len(info_rows) * row_h + 6; self.set_draw_color(185, 205, 228); self.set_line_width(0.3); self.rect(20, sign_y, 172, 22, "D")
        self.set_font(fn, "B", 8); self.set_text_color(100, 115, 140); self.set_xy(20, sign_y + 3); label_w = 172 / 3
        for label in ["진단 담당자", "검  토  자", "사  업  주"]: self.cell(label_w, 6, label, 0, 0, "C")
        for i in range(1, 3): self.line(20 + i * label_w, sign_y, 20 + i * label_w, sign_y + 22)
        self.set_fill_color(*BRAND_ACCENT); self.rect(0, 248, 210, 8, "F")
        self.set_y(249); self.set_font(fn, "B", 8); self.set_text_color(255, 255, 255); self.cell(0, 6, "AI 기반 환경관리 진단 시스템  |  Pilot Edition", 0, 0, "C")
        self.set_fill_color(228, 237, 250); self.rect(0, 256, 210, 41, "F")
        self.set_y(264); self.set_font(fn, "", 8); self.set_text_color(*BRAND_NAVY); self.cell(0, 5, f"보고 일자: {date_str}  |  비산배출 저감 자가진단 AI 시스템", 0, 0, "C")

    def draw_toc(self, toc_items):
        fn = self._fn()
        self.set_fill_color(*BRAND_LIGHT_BG); self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*BRAND_NAVY); self.rect(0, 0, 210, 20, "F")
        self.set_y(5); self.set_font(fn, "B", 12); self.set_text_color(220, 232, 248); self.cell(0, 10, "목    차  (Table of Contents)", 0, 1, "C"); self.ln(4)
        for title, page_hint in toc_items:
            is_sub = title.startswith("  "); self.set_x(22 if is_sub else 15); self.set_font(fn, "" if is_sub else "B", 9 if is_sub else 11); self.set_text_color(*(80, 95, 115) if is_sub else BRAND_NAVY)
            clean = title.strip(); dot_w = 150 - self.get_string_width(clean); dots = "." * max(int(dot_w / max(self.get_string_width("."), 0.1)), 3)
            self.cell(0, 7, f"{clean}  {dots}  {page_hint}", 0, 1, "L") 

    def draw_section_header(self, txt, set_section=True):
        fn = self._fn(); self.check_page_break(25); self.ln(2)
        if set_section: self._section = txt
        self.set_fill_color(*BRAND_ACCENT); self.rect(10, self.get_y(), 4, 11, "F")
        self.set_font(fn, "B", 13); self.set_text_color(*BRAND_NAVY); self.set_x(16); self.cell(0, 11, txt, 0, 1, "L")
        self.set_draw_color(*BRAND_ACCENT); self.set_line_width(0.4); self.line(10, self.get_y(), 200, self.get_y()); self.ln(2) 

    def draw_sub_header(self, txt):
        fn = self._fn(); self.check_page_break(15); self.ln(2)
        self.set_font(fn, "B", 10); self.set_text_color(*BRAND_ACCENT); self.set_x(12); self.cell(0, 7, txt, 0, 1, "L"); self.ln(1)

    def draw_zebra_table(self, headers, rows, col_widths, highlight_last_col=False):
        fn = self._fn(); self.set_fill_color(*BRAND_HEADER_BG); self.set_draw_color(175, 195, 220); self.set_line_width(0.2); self.set_font(fn, "B", 9); self.set_text_color(*BRAND_NAVY)
        for i, h in enumerate(headers): self.cell(col_widths[i], 8, h, border="TB", align="C", fill=True)
        self.ln(); self.set_font(fn, "", 8.5); self.set_text_color(35, 45, 60); alt = False
        if not rows: self.set_fill_color(*BRAND_LIGHT_BG); self.cell(sum(col_widths), 7, "추출된 데이터가 없습니다.", border="B", align="C", fill=True); self.ln(); return
        for row in rows:
            self.check_page_break(8); row_h = 7; self.set_fill_color(*(BRAND_LIGHT_BG if alt else (255, 255, 255)))
            for i, val in enumerate(row):
                cell_val = str(val); disp_val = cell_val if self.get_string_width(cell_val) <= col_widths[i] - 2 else cell_val[:int(col_widths[i]/3)] + ".."
                if highlight_last_col and i == len(row) - 1:
                    self.set_font(fn, "B", 8.5)
                    if any(x in cell_val for x in ["부적합", "불량", "High"]): self.set_text_color(*SCORE_COLORS["F"])
                    elif any(x in cell_val for x in ["적합", "양호"]): self.set_text_color(*SCORE_COLORS["A"])
                    elif "Medium" in cell_val: self.set_text_color(*SCORE_COLORS["C"])
                    else: self.set_text_color(35, 45, 60); self.set_font(fn, "", 8.5)
                else: self.set_text_color(35, 45, 60); self.set_font(fn, "", 8.5)
                self.cell(col_widths[i], row_h, disp_val, border="B", align="C", fill=True)
            self.ln(); alt = not alt

    def draw_grouped_table(self, headers, rows, col_widths, group_col_idx=0, highlight_last_col=False):
        fn = self._fn(); self.set_fill_color(*BRAND_HEADER_BG); self.set_draw_color(175, 195, 220); self.set_line_width(0.2); self.set_font(fn, "B", 9); self.set_text_color(*BRAND_NAVY)
        for i, h in enumerate(headers): self.cell(col_widths[i], 8, h, border="TB", align="C", fill=True)
        self.ln(); self.set_font(fn, "", 8.5); self.set_text_color(35, 45, 60)
        if not rows: self.set_fill_color(*BRAND_LIGHT_BG); self.cell(sum(col_widths), 7, "추출된 데이터가 없습니다.", border="B", align="C", fill=True); self.ln(); return
        current_group = None; alt_group = False
        for row in rows:
            self.check_page_break(8); group_val = str(row[group_col_idx])
            if current_group is None: current_group = group_val
            elif current_group != group_val: current_group = group_val; alt_group = not alt_group
            self.set_fill_color(*(BRAND_LIGHT_BG if alt_group else (255, 255, 255)))
            row_h = 7
            for i, val in enumerate(row):
                cell_val = str(val); disp_val = cell_val if self.get_string_width(cell_val) <= col_widths[i] - 2 else cell_val[:int(col_widths[i]/3)] + ".."
                if highlight_last_col and i == len(row) - 1:
                    self.set_font(fn, "B", 8.5)
                    if any(x in cell_val for x in ["부적합", "불량"]): self.set_text_color(*SCORE_COLORS["F"])
                    elif any(x in cell_val for x in ["적합", "양호"]): self.set_text_color(*SCORE_COLORS["A"])
                    else: self.set_text_color(35, 45, 60); self.set_font(fn, "", 8.5)
                else: self.set_text_color(35, 45, 60); self.set_font(fn, "", 8.5)
                self.cell(col_widths[i], row_h, disp_val, border="B", align="C", fill=True)
            self.ln()

    def draw_aq_status_cards(self, o3_str, pm10_str):
        fn = self._fn(); self.check_page_break(30); o3_f = float(str(o3_str)) if str(o3_str) not in ("-", "", "None") else 0.0; pm10_f = float(str(pm10_str)) if str(pm10_str) not in ("-", "", "None") else 0.0
        o3_status, o3_color = ("나쁨", SCORE_COLORS["D"]) if o3_f > 0.09 else ("보통", SCORE_COLORS["B"])
        pm10_status, pm10_color = ("나쁨", SCORE_COLORS["D"]) if pm10_f > 80 else ("보통", SCORE_COLORS["B"])
        card_data = [("오존 (O3)", f"{o3_str} ppm", o3_status, o3_color), ("미세먼지 (PM10)", f"{pm10_str} ug/m3", pm10_status, pm10_color)]
        card_w = 90; gap = 10; start_x = 10; card_h = 24; start_y = self.get_y()
        for i, (label, value, status, color) in enumerate(card_data):
            cx = start_x + i * (card_w + gap); r, g, b = color; lr, lg, lb = min(r + 75, 255), min(g + 75, 255), min(b + 75, 255); dr, dg, db = max(r - 25, 0), max(g - 25, 0), max(b - 25, 0)
            self.set_fill_color(248, 251, 255); self.set_draw_color(205, 218, 238); self.set_line_width(0.25); self.rect(cx, start_y, card_w, card_h, "FD")
            self.set_fill_color(r, g, b); self.rect(cx, start_y, 4, card_h, "F")
            self.set_font(fn, "B", 8); self.set_text_color(*BRAND_NAVY); self.set_xy(cx + 7, start_y + 3); self.cell(card_w - 40, 5, label, 0, 0, "L")
            self.set_fill_color(lr, lg, lb); self.rect(cx + card_w - 30, start_y + 2, 26, 8, "F")
            self.set_font(fn, "B", 8); self.set_text_color(dr, dg, db); self.set_xy(cx + card_w - 30, start_y + 3); self.cell(26, 6, status, 0, 0, "C")
            self.set_font(fn, "B", 12); self.set_text_color(r, g, b); self.set_xy(cx + 7, start_y + 10); self.cell(card_w - 14, 9, value, 0, 0, "L")
        self.set_y(start_y + card_h + 2) 

    def draw_scorecard(self, scores_data: dict):
        fn = self._fn(); self.check_page_break(40); items = [("관리자 선임", scores_data.get("manager_score", {}).get("score", 0)), ("방지시설 기준", scores_data.get("prevention_score", {}).get("score", 0)), ("LDAR 점검", scores_data.get("ldar_score", {}).get("score", 0)), ("기록 충실성", scores_data.get("record_score", {}).get("score", 0))]
        total = int(scores_data.get("overall_score", {}).get("score", 0)); grade_total = scores_data.get("overall_score", {}).get("grade", "F")
        card_x = 10; card_w = 33; gap = 2; sep = 4; total_w = 37; card_h = 30; start_y = self.get_y()
        for idx, (label, score_val) in enumerate(items):
            score = int(score_val); cx = card_x + idx * (card_w + gap); cy = start_y
            grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
            r, g, b = SCORE_COLORS.get(grade, (100, 100, 100)); lr, lg, lb = min(r + 65, 255), min(g + 65, 255), min(b + 65, 255); dr, dg, db = max(r - 25, 0), max(g - 25, 0), max(b - 25, 0)
            self.set_fill_color(250, 251, 254); self.set_draw_color(210, 220, 238); self.set_line_width(0.35); self.rect(cx, cy, card_w, card_h, "FD")
            self.set_fill_color(r, g, b); self.rect(cx, cy, 3, card_h, "F")
            self.set_fill_color(lr, lg, lb); self.rect(cx + card_w - 10, cy + 2, 8, 8, "F")
            self.set_font(fn, "B", 7); self.set_text_color(dr, dg, db); self.set_xy(cx + card_w - 10, cy + 3); self.cell(8, 6, grade, 0, 0, "C")
            self.set_font(fn, "", 7); self.set_text_color(110, 122, 145); self.set_xy(cx + 4, cy + 3); self.cell(card_w - 14, 5, label, 0, 0, "L")
            self.set_font(fn, "B", 17); self.set_text_color(r, g, b); self.set_xy(cx + 4, cy + 8); self.cell(card_w - 8, 13, str(score), 0, 0, "C")
            self.set_fill_color(215, 222, 235); self.rect(cx + 4, cy + card_h - 5, card_w - 8, 3, "F")
            self.set_fill_color(r, g, b); self.rect(cx + 4, cy + card_h - 5, (card_w - 8) * max(0, min(100, score)) / 100, 3, "F")
        tcx = card_x + 4 * card_w + 3 * gap + sep; tr, tg, tb = SCORE_COLORS.get(grade_total, BRAND_ACCENT); tlr, tlg, tlb = min(tr + 65, 255), min(tg + 65, 255), min(tb + 65, 255); tdr, tdg, tdb = max(tr - 30, 0), max(tg - 30, 0), max(tb - 30, 0)
        self.set_fill_color(tlr, tlg, tlb); self.set_draw_color(tr, tg, tb); self.set_line_width(0.5); self.rect(tcx, start_y, total_w, card_h, "FD")
        self.set_font(fn, "B", 8); self.set_text_color(tdr, tdg, tdb); self.set_xy(tcx, start_y + 3); self.cell(total_w, 6, "종 합 등 급", 0, 1, "C")
        self.set_font(fn, "B", 22); self.set_text_color(tdr, tdg, tdb); self.set_xy(tcx, start_y + 8); self.cell(total_w, 14, grade_total, 0, 1, "C")
        self.set_font(fn, "", 8); self.set_text_color(90, 100, 115); self.set_xy(tcx, start_y + 23); self.cell(total_w, 5, f"총점 {total}점", 0, 0, "C"); self.ln(card_h + 2)

    def draw_text_box(self, text: str, title: str = ""):
        fn = self._fn(); x = 10; w = 190; estimated_height = len(text.split("\n")) * 7 + 10; self.check_page_break(estimated_height)
        if title: self.set_font(fn, "B", 10); self.set_text_color(*BRAND_NAVY); self.set_x(x + 2); self.cell(0, 6, title, 0, 1, "L")
        for line in text.split("\n"):
            line = line.strip()
            if not line: self.ln(1); continue
            if re.match(r"^【\d+\.", line): self.set_font(fn, "B", 10); self.set_text_color(*BRAND_NAVY); self.set_x(x + 4); self.multi_cell(w - 4, 6, line); self.ln(1)
            elif line.startswith("▶"): self.set_font(fn, "B", 9); self.set_text_color(*BRAND_ACCENT); self.set_x(x + 6); self.multi_cell(w - 6, 6, line)
            elif re.match(r"^\d+\.", line): self.set_font(fn, "B", 9); self.set_text_color(40, 50, 65); self.set_x(x + 4); self.multi_cell(w - 4, 6, line)
            else: self.set_font(fn, "", 9.5); self.set_text_color(55, 65, 80); self.set_x(x + 8); self.multi_cell(w - 8, 6.5, line)
        self.ln(2)

def create_gov_report_pdf(ai_data: dict, user_info: dict, air_advice: str, air_data: dict, station_name: str) -> bytes:
    now_str = datetime.now().strftime("%Y년 %m월 %d일"); data = ai_data.get("parsed", {}); scores = data.get("scores", {})
    toc_items = [("가. 사업장 및 진단 개요", "1"), ("나. 준수율 종합 스코어카드", "1"), ("다. 공공데이터 기반 지역 환경 분석", "2"), ("라. 시설별 정밀 진단 내역 (전수조사)", "3"), ("마. 위험도 매트릭스 및 행정처분 가능성", "4"), ("바. AI 정밀 진단 종합 의견 및 중장기 로드맵", "5"), ("사. 관련 규제 및 행정처분 참고사항", "6"), ("아. 비산배출시설 변경신고 및 추진체계", "6")]
    pdf = ProfessionalPDF(toc_data=toc_items); pdf._reg_fonts(); pdf.set_auto_page_break(auto=True, margin=15)
    company_name = user_info.get("name", "-"); address_str = user_info.get("addr", "-"); industry_str = user_info.get("industry", "-")
    pdf.add_page(); pdf.draw_cover(company=company_name, address=address_str, industry=industry_str, permit_no=user_info.get("permit_no", "-"), date_str=now_str)
    pdf.add_page(); pdf.draw_toc(toc_items)
    pdf.add_page(); pdf.draw_section_header("가. 사업장 및 진단 개요"); pdf.draw_sub_header("1) 기본 정보 요약표")
    overview_rows = [["사업장명", company_name, "소재지", address_str], ["대표자", user_info.get("rep", "-"), "업종 분류", industry_str], ["허가·신고 번호", user_info.get("permit_no", "-"), "진단 일자", now_str]]
    pdf.draw_zebra_table(["항목", "내용", "항목", "내용"], overview_rows, [32, 63, 32, 63])
    pdf.draw_section_header("나. 준수율 종합 스코어카드"); pdf.draw_scorecard(scores)
    pdf.add_page(); pdf.draw_section_header("다. 공공데이터 기반 지역 환경 분석")
    pdf.draw_aq_status_cards(air_data.get("o3Value", "-"), air_data.get("pm10Value", "-")); pdf.draw_text_box(air_advice)
    pdf.add_page(); pdf.draw_section_header("라. 시설별 정밀 진단 내역 (전수조사)")
    pdf.draw_sub_header("1) 방지시설 배출농도 추이 (THC)")
    prev_rows = [[p.get("period","-"), p.get("date","-"), p.get("facility","-"), p.get("value","-"), p.get("limit","-"), p.get("result","-")] for p in data.get("prevention", {}).get("data", [])]
    pdf.draw_grouped_table(["구분", "측정일", "시설명", "결과", "기준", "판정"], prev_rows, [30, 25, 60, 25, 25, 25], highlight_last_col=True)
    pdf.draw_sub_header("2) 비산누출시설 LDAR 점검 실적")
    ldar_rows = [[d.get("year","-"), d.get("target_count","-"), d.get("leak_count","-"), d.get("leak_rate","-"), d.get("result","-")] for d in data.get("ldar", {}).get("data", [])]
    pdf.draw_zebra_table(["연도", "대상개소", "누출수", "누출률", "판정"], ldar_rows, [30, 40, 40, 40, 40], highlight_last_col=True)
    pdf.add_page(); pdf.draw_section_header("바. AI 정밀 진단 종합 의견 및 중장기 로드맵")
    pdf.draw_text_box(data.get("overall_opinion", "-"), title="전문가 종합 의견")
    
    # ★ 이미지(추진체계) 개선 영역
    pdf.add_page(); pdf.draw_section_header("아. 비산배출시설 변경신고 및 추진체계"); pdf.ln(10)
    pdf.draw_sub_header("1) 비산배출 저감제도 주요 추진체계 (시각화)"); pdf.ln(5)
    sy = pdf.get_y(); fn = pdf._fn(); pdf.set_draw_color(*BRAND_ACCENT); pdf.set_line_width(0.4)
    boxes = [("기후에너지환경부", "제도 총괄 및 가이드라인 수립", 15, 85), ("관할 환경청", "신고 수리 및 지도 점검", 105, 90), ("한국환경공단", "정기점검 및 기술 지원", 15, 85), ("대상 사업장", "시설 관리기준 준수 및 운영기록", 105, 90)]
    for i, (title, desc, bx, bw) in enumerate(boxes):
        row = i // 2; ry = sy + (row * 35)
        pdf.set_fill_color(*BRAND_LIGHT_BG); pdf.rect(bx, ry, bw, 28, "DF")
        pdf.set_xy(bx, ry + 4); pdf.set_font(fn, "B", 10); pdf.set_text_color(*BRAND_NAVY); pdf.cell(bw, 6, title, 0, 1, "C")
        pdf.set_xy(bx, ry + 12); pdf.set_font(fn, "", 9); pdf.set_text_color(60, 70, 90); pdf.multi_cell(bw, 5, desc, align="C")
    return bytes(pdf.output())
