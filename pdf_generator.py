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
        self.ln(4)

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
        self.set_fill_color(*BRAND_LIGHT_BG)
        self.rect(0, 0, 210, 297, "F")

        self.set_fill_color(*BRAND_NAVY)
        self.rect(0, 0, 210, 26, "F")
        self.set_y(8)
        self.set_font(fn, "B", 10)
        self.set_text_color(220, 232, 248)
        self.cell(0, 8, "한국환경공단 비산배출 자가진단 시스템 (시범사업)  |  v105.1 Modular", 0, 1, "C")

        self.set_fill_color(*BRAND_ACCENT)
        self.rect(0, 26, 7, 271, "F")

        self.set_fill_color(255, 255, 255)
        self.set_draw_color(195, 212, 235)
        self.set_line_width(0.5)
        self.rect(16, 38, 178, 198, "FD")

        self.set_fill_color(*BRAND_ACCENT)
        self.rect(16, 38, 178, 15, "F")
        self.set_y(41)
        self.set_font(fn, "B", 14)
        self.set_text_color(255, 255, 255)
        self.cell(0, 9, "비산배출시설 정밀 자가진단 보고서", 0, 1, "C")

        self.set_y(56)
        self.set_font(fn, "B", 9)
        self.set_text_color(*BRAND_NAVY)
        self.cell(0, 6, "HAPs 비산배출시설 환경관리 적합성 정밀 진단", 0, 1, "C")

        self.set_draw_color(*BRAND_ACCENT)
        self.set_line_width(0.35)
        self.line(24, 64, 194, 64)

        info_y    = 69
        row_h     = 12
        info_rows = [
            ("진단 대상 사업장", company),
            ("소        재        지", address),
            ("업    종    분    류", industry),
            ("허  가  신  고  번  호", permit_no),
            ("보    고    일    자", date_str),
        ]
        for i, (k, v) in enumerate(info_rows):
            if i % 2 == 0: self.set_fill_color(*BRAND_LIGHT_BG)
            else: self.set_fill_color(255, 255, 255)
            self.set_xy(20, info_y + i * row_h)
            self.set_font(fn, "B", 9)
            self.set_text_color(*BRAND_NAVY)
            self.cell(50, row_h - 1, k, 0, 0, "R", fill=True)
            self.set_font(fn, "", 9)
            self.set_text_color(30, 40, 60)
            self.cell(130, row_h - 1, " " + v.replace('\n', ' '), 0, 0, "L", fill=True)

        sign_y = info_y + len(info_rows) * row_h + 6
        self.set_draw_color(185, 205, 228)
        self.set_line_width(0.3)
        self.rect(20, sign_y, 172, 22, "D")
        self.set_font(fn, "B", 8)
        self.set_text_color(100, 115, 140)
        self.set_xy(20, sign_y + 3)
        label_w = 172 / 3
        for label in ["진단 담당자", "검  토  자", "사  업  주"]:
            self.cell(label_w, 6, label, 0, 0, "C")
        for i in range(1, 3):
            self.line(20 + i * label_w, sign_y, 20 + i * label_w, sign_y + 22)

        self.set_fill_color(*BRAND_ACCENT)
        self.rect(0, 248, 210, 8, "F")
        self.set_y(249)
        self.set_font(fn, "B", 8)
        self.set_text_color(255, 255, 255)
        self.cell(0, 6, "AI 기반 환경관리 진단 시스템  |  Pilot Edition", 0, 0, "C")

        self.set_fill_color(228, 237, 250)
        self.rect(0, 256, 210, 41, "F")
        self.set_y(264)
        self.set_font(fn, "", 8)
        self.set_text_color(*BRAND_NAVY)
        self.cell(0, 5, f"보고 일자: {date_str}  |  비산배출 저감 자가진단 AI 시스템", 0, 0, "C")

    def draw_toc(self, toc_items):
        fn = self._fn()
        self.set_fill_color(*BRAND_LIGHT_BG)
        self.rect(0, 0, 210, 297, "F")

        self.set_fill_color(*BRAND_NAVY)
        self.rect(0, 0, 210, 20, "F")
        self.set_y(5)
        self.set_font(fn, "B", 12)
        self.set_text_color(220, 232, 248)
        self.cell(0, 10, "목    차  (Table of Contents)", 0, 1, "C")
        self.ln(4)

        for title, page_hint in toc_items:
            is_sub = title.startswith("  ")
            if not is_sub:
                self.set_x(15)
                self.set_font(fn, "B", 11)
                self.set_text_color(*BRAND_NAVY)
            else:
                self.set_x(22)
                self.set_font(fn, "", 9)
                self.set_text_color(80, 95, 115)
            clean  = title.strip()
            dot_w  = 150 - self.get_string_width(clean)
            dots   = "." * max(int(dot_w / max(self.get_string_width("."), 0.1)), 3)
            self.cell(0, 7, f"{clean}  {dots}  {page_hint}", 0, 1, "L") 

    def draw_section_header(self, txt, set_section=True):
        fn = self._fn()
        self.check_page_break(25) 
        self.ln(2)
        if set_section: self._section = txt
        self.set_fill_color(*BRAND_ACCENT)
        self.rect(10, self.get_y(), 4, 11, "F")
        self.set_font(fn, "B", 13)
        self.set_text_color(*BRAND_NAVY)
        self.set_x(16)
        self.cell(0, 11, txt, 0, 1, "L")
        self.set_draw_color(*BRAND_ACCENT)
        self.set_line_width(0.4)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2) 

    def draw_sub_header(self, txt):
        fn = self._fn()
        self.check_page_break(15)
        self.ln(2)
        self.set_font(fn, "B", 10)
        self.set_text_color(*BRAND_ACCENT)
        self.set_x(12)
        self.cell(0, 7, txt, 0, 1, "L")
        self.ln(1)

    def get_truncated_text(self, text, max_w):
        if self.get_string_width(text) <= max_w - 2: return text
        for length in range(len(text), 0, -1):
            temp = text[:length] + ".."
            if self.get_string_width(temp) <= max_w - 2: return temp
        return ".."

    def draw_zebra_table(self, headers, rows, col_widths, highlight_last_col=False):
        fn = self._fn()
        self.set_fill_color(*BRAND_HEADER_BG)
        self.set_draw_color(175, 195, 220)
        self.set_line_width(0.2)
        self.set_font(fn, "B", 9)
        self.set_text_color(*BRAND_NAVY)
        
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 8, h, border="TB", align="C", fill=True)
        self.ln()

        self.set_font(fn, "", 8.5)
        self.set_text_color(35, 45, 60)
        alt = False

        if not rows:
            self.set_fill_color(*BRAND_LIGHT_BG)
            self.cell(sum(col_widths), 7, "추출된 데이터가 없습니다.", border="B", align="C", fill=True)
            self.ln()
            return

        for row in rows:
            self.check_page_break(8) 
            row_h = 7
            if alt: self.set_fill_color(*BRAND_LIGHT_BG)
            else: self.set_fill_color(255, 255, 255)

            for i, val in enumerate(row):
                cell_val = str(val)
                disp_val = self.get_truncated_text(cell_val, col_widths[i])

                if highlight_last_col and i == len(row) - 1:
                    if "부적합" in cell_val or "불량" in cell_val:
                        self.set_text_color(*SCORE_COLORS["F"]); self.set_font(fn, "B", 8.5)
                    elif "적합" in cell_val or "양호" in cell_val:
                        self.set_text_color(*SCORE_COLORS["A"]); self.set_font(fn, "B", 8.5)
                    elif cell_val in ("High",):
                        self.set_text_color(*SCORE_COLORS["D"]); self.set_font(fn, "B", 8.5)
                    elif cell_val in ("Medium",):
                        self.set_text_color(*SCORE_COLORS["C"]); self.set_font(fn, "B", 8.5)
                    else:
                        self.set_text_color(35, 45, 60); self.set_font(fn, "", 8.5)
                else:
                    self.set_text_color(35, 45, 60); self.set_font(fn, "", 8.5)
                
                self.cell(col_widths[i], row_h, disp_val, border="B", align="C", fill=True)
            self.ln()
            alt = not alt

    def draw_grouped_table(self, headers, rows, col_widths, group_col_idx=0, highlight_last_col=False):
        fn = self._fn()
        self.set_fill_color(*BRAND_HEADER_BG)
        self.set_draw_color(175, 195, 220)
        self.set_line_width(0.2)
        self.set_font(fn, "B", 9)
        self.set_text_color(*BRAND_NAVY)
        
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 8, h, border="TB", align="C", fill=True)
        self.ln()

        self.set_font(fn, "", 8.5)
        self.set_text_color(35, 45, 60)
        
        if not rows:
            self.set_fill_color(*BRAND_LIGHT_BG)
            self.cell(sum(col_widths), 7, "추출된 데이터가 없습니다.", border="B", align="C", fill=True)
            self.ln()
            return

        current_group = None
        alt_group = False

        for row in rows:
            self.check_page_break(8)
            group_val = str(row[group_col_idx])
            
            if current_group is None:
                current_group = group_val
            elif current_group != group_val:
                current_group = group_val
                alt_group = not alt_group

            if alt_group: self.set_fill_color(*BRAND_LIGHT_BG) 
            else: self.set_fill_color(255, 255, 255)         

            row_h = 7
            for i, val in enumerate(row):
                cell_val = str(val)
                disp_val = self.get_truncated_text(cell_val, col_widths[i])

                if highlight_last_col and i == len(row) - 1:
                    if "부적합" in cell_val or "불량" in cell_val:
                        self.set_text_color(*SCORE_COLORS["F"]); self.set_font(fn, "B", 8.5)
                    elif "적합" in cell_val or "양호" in cell_val:
                        self.set_text_color(*SCORE_COLORS["A"]); self.set_font(fn, "B", 8.5)
                    else:
                        self.set_text_color(35, 45, 60); self.set_font(fn, "", 8.5)
                else:
                    self.set_text_color(35, 45, 60); self.set_font(fn, "", 8.5)
                
                self.cell(col_widths[i], row_h, disp_val, border="B", align="C", fill=True)
            self.ln()

    def draw_aq_status_cards(self, o3_str, pm10_str):
        fn = self._fn()
        self.check_page_break(30)
        try: o3_f = float(str(o3_str)) if str(o3_str) not in ("-", "", "None") else 0.0
        except: o3_f = 0.0
        try: pm10_f = float(str(pm10_str)) if str(pm10_str) not in ("-", "", "None") else 0.0
        except: pm10_f = 0.0

        o3_status, o3_color = "보통", SCORE_COLORS["B"] # 간소화: utils에서 판별해도 좋음
        pm10_status, pm10_color = "보통", SCORE_COLORS["B"]
        if o3_f > 0.09: o3_status, o3_color = "나쁨", SCORE_COLORS["D"]
        if pm10_f > 80: pm10_status, pm10_color = "나쁨", SCORE_COLORS["D"]

        card_data = [
            ("오존 (O3)",         f"{o3_str} ppm",   o3_status,   o3_color),
            ("미세먼지 (PM10)", f"{pm10_str} ug/m3", pm10_status, pm10_color),
        ]

        card_w  = 90; gap = 10; start_x = 10; card_h = 24
        start_y = self.get_y()

        for i, (label, value, status, color) in enumerate(card_data):
            cx  = start_x + i * (card_w + gap)
            r, g, b = color
            lr = min(r + 75, 255); lg = min(g + 75, 255); lb = min(b + 75, 255)
            dr = max(r - 25, 0); dg = max(g - 25, 0); db = max(b - 25, 0)

            self.set_fill_color(248, 251, 255); self.set_draw_color(205, 218, 238)
            self.set_line_width(0.25)
            self.rect(cx, start_y, card_w, card_h, "FD")
            self.set_fill_color(r, g, b); self.rect(cx, start_y, 4, card_h, "F")

            self.set_font(fn, "B", 8); self.set_text_color(*BRAND_NAVY)
            self.set_xy(cx + 7, start_y + 3)
            self.cell(card_w - 40, 5, label, 0, 0, "L")

            badge_x = cx + card_w - 30; badge_y = start_y + 2
            self.set_fill_color(lr, lg, lb); self.rect(badge_x, badge_y, 26, 8, "F")
            self.set_font(fn, "B", 8); self.set_text_color(dr, dg, db)
            self.set_xy(badge_x, badge_y + 1); self.cell(26, 6, status, 0, 0, "C")

            self.set_font(fn, "B", 12); self.set_text_color(r, g, b)
            self.set_xy(cx + 7, start_y + 10); self.cell(card_w - 14, 9, value, 0, 0, "L")

        self.set_y(start_y + card_h + 2) 

    def draw_scorecard(self, scores_data: dict):
        fn = self._fn()
        self.check_page_break(40)
        items = [
            ("관리자 선임",   scores_data.get("manager_score",   {}).get("score", 0)),
            ("방지시설 기준", scores_data.get("prevention_score", {}).get("score", 0)),
            ("LDAR 점검",   scores_data.get("ldar_score",        {}).get("score", 0)),
            ("기록 충실성",   scores_data.get("record_score",      {}).get("score", 0)),
        ]
        
        try: total = int(scores_data.get("overall_score", {}).get("score", 0))
        except: total = 0
        grade_total = scores_data.get("overall_score", {}).get("grade",  "F")

        card_x  = 10; card_w  = 33; gap = 2; sep = 4; total_w = 37; card_h  = 30
        start_y = self.get_y()

        for idx, (label, score_val) in enumerate(items):
            try: score = int(score_val)
            except: score = 0
            cx = card_x + idx * (card_w + gap); cy = start_y

            if score >= 90: grade = "A"
            elif score >= 80: grade = "B"
            elif score >= 70: grade = "C"
            elif score >= 60: grade = "D"
            else: grade = "F"

            r, g, b = SCORE_COLORS.get(grade, (100, 100, 100))
            lr = min(r + 65, 255); lg = min(g + 65, 255); lb = min(b + 65, 255)
            dr = max(r - 25, 0); dg = max(g - 25, 0); db = max(b - 25, 0)

            self.set_fill_color(250, 251, 254); self.set_draw_color(210, 220, 238)
            self.set_line_width(0.35)
            self.rect(cx, cy, card_w, card_h, "FD")
            self.set_fill_color(r, g, b); self.rect(cx, cy, 3, card_h, "F")

            bx = cx + card_w - 10; by = cy + 2
            self.set_fill_color(lr, lg, lb); self.rect(bx, by, 8, 8, "F")
            self.set_font(fn, "B", 7); self.set_text_color(dr, dg, db)
            self.set_xy(bx, by + 1); self.cell(8, 6, grade, 0, 0, "C")

            self.set_font(fn, "", 7); self.set_text_color(110, 122, 145)
            self.set_xy(cx + 4, cy + 3); self.cell(card_w - 14, 5, label, 0, 0, "L")

            self.set_font(fn, "B", 17); self.set_text_color(r, g, b)
            self.set_xy(cx + 4, cy + 8); self.cell(card_w - 8, 13, str(score), 0, 0, "C")

            bar_y = cy + card_h - 5
            self.set_fill_color(215, 222, 235)
            self.rect(cx + 4, bar_y, card_w - 8, 3, "F")
            self.set_fill_color(r, g, b)
            self.rect(cx + 4, bar_y, (card_w - 8) * max(0, min(100, score)) / 100, 3, "F")

        total_cx = card_x + 4 * card_w + 3 * gap + sep
        tr, tg, tb = SCORE_COLORS.get(grade_total, BRAND_ACCENT)
        tlr = min(tr + 65, 255); tlg = min(tg + 65, 255); tlb = min(tb + 65, 255)
        tdr = max(tr - 30, 0); tdg = max(tg - 30, 0); tdb = max(tb - 30, 0)

        self.set_fill_color(tlr, tlg, tlb); self.set_draw_color(tr, tg, tb)
        self.set_line_width(0.5)
        self.rect(total_cx, start_y, total_w, card_h, "FD")

        self.set_font(fn, "B", 8); self.set_text_color(tdr, tdg, tdb)
        self.set_xy(total_cx, start_y + 3); self.cell(total_w, 6, "종 합 등 급", 0, 1, "C")

        self.set_font(fn, "B", 22); self.set_text_color(tdr, tdg, tdb)
        self.set_xy(total_cx, start_y + 8); self.cell(total_w, 14, grade_total, 0, 1, "C")

        self.set_font(fn, "", 8); self.set_text_color(90, 100, 115)
        self.set_xy(total_cx, start_y + 23); self.cell(total_w, 5, f"총점 {total}점", 0, 0, "C")
        self.ln(card_h + 2)

    def draw_text_box(self, text: str, title: str = ""):
        fn = self._fn()
        x = 10; w = 190
        estimated_height = len(text.split("\n")) * 7 + 10
        self.check_page_break(estimated_height)

        if title:
            self.set_font(fn, "B", 10); self.set_text_color(*BRAND_NAVY)
            self.set_x(x + 2); self.cell(0, 6, title, 0, 1, "L")

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                self.ln(1); continue
            if re.match(r"^【\d+\.", line):
                self.set_font(fn, "B", 10); self.set_text_color(*BRAND_NAVY)
                self.set_x(x + 4); self.multi_cell(w - 4, 6, line); self.ln(1)
            elif line.startswith("▶"):
                self.set_font(fn, "B", 9); self.set_text_color(*BRAND_ACCENT)
                self.set_x(x + 6); self.multi_cell(w - 6, 6, line)
            elif re.match(r"^\d+\.", line):
                self.set_font(fn, "B", 9); self.set_text_color(40, 50, 65)
                self.set_x(x + 4); self.multi_cell(w - 4, 6, line)
            else:
                self.set_font(fn, "", 9.5); self.set_text_color(55, 65, 80)
                self.set_x(x + 8); self.multi_cell(w - 8, 6.5, line)
        self.ln(2)

# ★ 5개의 인자를 정확히 받도록 수정 완료 (map_coord 제거)
def create_gov_report_pdf(ai_data: dict, user_info: dict, air_advice: str, air_data: dict, station_name: str) -> bytes:
    now_str = datetime.now().strftime("%Y년 %m월 %d일")
    data    = ai_data.get("parsed", {})
    scores  = data.get("scores", {})

    process_emission_data = data.get("process_emission", {}).get("data", [])
    has_process_emission = len(process_emission_data) > 0

    toc_items = [
        ("가. 사업장 및 진단 개요",                "1"),
        ("  - 1) 기본 정보 요약표",               "1"),
        ("나. 준수율 종합 스코어카드",             "1"),
        ("  - 1) 항목별 점수 및 등급",             "1"),
        ("다. 공공데이터 기반 지역 환경 분석",     "2"),
        ("  - 1) 주요 대기질 상태 인포그래픽",     "2"),
        ("  - 2) 실시간 대기질 현황",             "2"),
        ("  - 3) 전문가 제언 및 관리 지침",       "2"),
        ("라. 시설별 정밀 진단 내역 (전수조사)",   "3"),
        ("  - 1) 관리담당자 선임 현황",           "3"),
        ("  - 2) 방지시설 배출농도 추이 (THC)",   "3"),
    ]
    
    if has_process_emission:
        toc_items.append(("  - 3) 공정배출시설 측정 결과 (냉각탑 등)", "3"))
        ldar_idx = "4"
    else:
        ldar_idx = "3"

    toc_items.extend([
        (f"  - {ldar_idx}) 비산누출시설(LDAR) 점검 실적", "4"),
        ("마. 위험도 매트릭스 및 행정처분 가능성", "4"),
        ("바. AI 종합 진단 및 중장기 개선 권고",   "5"),
        ("사. 관련 규제 및 행정처분 참고사항",     "5"),
        ("아. 자가 체크리스트 (점검표)",           "6"),
    ])

    pdf = ProfessionalPDF(toc_data=toc_items)
    pdf._reg_fonts()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.add_page()
    pdf.draw_cover(company=user_info["company"], address=user_info["address"], industry=user_info["industry"], permit_no=user_info.get("permit_no", "-"), date_str=now_str)

    pdf.add_page()
    pdf.draw_toc(toc_items)

    pdf.add_page()
    pdf.draw_section_header("가. 사업장 및 진단 개요")
    pdf.draw_sub_header("1) 기본 정보 요약표")

    env_office = get_env_office(user_info["address"])
    
    # ★ 안전한 데이터 타임 가져오기
    data_time = air_data.get("dataTime", datetime.now().strftime("%Y-%m-%d %H:00")) if air_data else datetime.now().strftime("%Y-%m-%d %H:00")

    overview_rows = [
        ["사업장명",        user_info["company"],                  "사업자등록번호", user_info.get("biz_no", "-")],
        ["소재지",          user_info["address"],                  "관할 환경청",    env_office],
        ["대표자",          user_info["rep"],                      "업종 분류",      user_info["industry"]],
        ["허가·신고 번호",  user_info.get("permit_no", "-"),       "THC 배출기준",   get_limit_ppm(user_info["industry"])],
        ["담당자 연락처",   user_info.get("tel", "-"),             "진단 일자",      now_str],
        ["진단 수행 기관",  "비산배출 AI 자가진단 시스템",         "시스템 버전",    "Professional v105.1"],
        ["관할 대기측정소", station_name,                          "진단 범위",      "다개년 운영기록 전수 추출"],
        ["주요 배출 공정",  "(운영기록부 기재 기준)",              "주요 오염물질",  "VOCs / THC / LDAR 대상물질"],
    ]
    pdf.draw_zebra_table(["항목", "내용", "항목", "내용"], overview_rows, [32, 63, 32, 63])
    
    pdf.draw_section_header("나. 준수율 종합 스코어카드")
    pdf.draw_sub_header("1) 항목별 준수율 점수 및 등급")
    pdf.draw_scorecard(scores)

    score_rows = []
    for key, label in [("manager_score", "관리담당자 선임"), ("prevention_score", "공정/방지시설 기준"), ("ldar_score", "LDAR 누출 점검"), ("record_score", "운영기록 충실성")]:
        s = scores.get(key, {})
        score_rows.append([label, str(s.get("score", "-")), s.get("grade", "-"), s.get("reason", "-")])
    pdf.draw_zebra_table(["평가 항목", "점수", "등급", "근거 요약"], score_rows, [45, 20, 20, 105])

    pdf.draw_section_header("다. 공공데이터 기반 지역 환경 분석")
    o3   = air_data.get("o3Value",   "-") if air_data else "-"
    pm10 = air_data.get("pm10Value", "-") if air_data else "-"
    pm25 = air_data.get("pm25Value", "-") if air_data else "-"
    no2  = air_data.get("no2Value",  "-") if air_data else "-"
    so2  = air_data.get("so2Value",  "-") if air_data else "-"
    co   = air_data.get("coValue",   "-") if air_data else "-"

    # ★ 측정소 이름이 반영된 제목
    pdf.draw_sub_header(f"1) 주요 대기질 상태 인포그래픽 (관할: {station_name} 측정소, 기준: {data_time})")
    pdf.draw_aq_status_cards(o3, pm10)

    pdf.draw_sub_header("2) 실시간 대기질 현황 (관할 측정소 전체)")
    aq_rows = [
        ["오존 (O3)",         f"{o3} ppm",    "보통",   "0.06ppm",  "VOCs 광화학 반응에 의한 2차 오염물질"],
        ["미세먼지(PM10)",    f"{pm10} ug/m3", "보통", "80 ug/m3", "비산 분진(먼지) 발생과 직접 연관"],
        ["초미세먼지(PM2.5)", f"{pm25} ug/m3", "보통", "35 ug/m3", "연소시설 배출 연관"],
        ["이산화질소(NO2)",   f"{no2} ppm",    "-",             "0.06ppm",  "질소산화물 관리 참고"],
        ["이산화황 (SO2)",    f"{so2} ppm",    "-",             "0.02ppm",  "황 함유 원료 사용 사업장 주의"],
        ["일산화탄소(CO)",    f"{co} ppm",     "-",             "9ppm",     "불완전 연소 지표"],
    ]
    pdf.draw_zebra_table(["오염물질", "현재 농도", "상태", "대기환경 기준", "사업장 연관성"], aq_rows, [30, 22, 15, 28, 95])

    pdf.draw_sub_header("3) 전문가 제언 및 환경관리 지침")
    pdf.draw_text_box(air_advice if air_advice else "대기질 정보를 불러오지 못했습니다.")

    pdf.draw_section_header("라. 시설별 정밀 진단 내역 (전수 조사)")

    pdf.draw_sub_header("1) 관리담당자 선임 현황")
    mgr      = data.get("manager", {})
    mgr_rows = [[m.get("period","-"), m.get("name","-"), m.get("dept","-"), m.get("date","-"), m.get("qualification","-")] for m in mgr.get("data", [])]
    pdf.draw_zebra_table(["기간", "담당자명", "소속 부서", "선임일", "자격/비고"], mgr_rows, [30, 35, 45, 30, 50])
    if mgr.get("analysis"): pdf.draw_text_box(mgr["analysis"], title="📋 관리담당자 분석 의견")

    pdf.draw_sub_header("2) 방지시설 배출농도 추이 (THC)")
    prev      = data.get("prevention", {})
    prev_data_list = prev.get("data", [])
    try: prev_data_list.sort(key=lambda x: str(x.get("period", "")))
    except: pass
    prev_rows = [[p.get("period","-"), p.get("date","-"), p.get("facility","-"), p.get("value","-"), p.get("limit", get_limit_ppm(user_info["industry"])), p.get("accuracy_check","-"), p.get("result","-")] for p in prev_data_list]
    pdf.draw_grouped_table(["구분(반기)", "측정일", "방지시설명", "측정결과", "기준", "증빙", "판정"], prev_rows, [30, 25, 55, 25, 20, 15, 20], highlight_last_col=True)
    
    if prev.get("trend_summary"): pdf.draw_text_box(prev["trend_summary"], title="📈 THC 측정결과 추이 분석")
    if prev.get("analysis"): pdf.draw_text_box(prev["analysis"], title="📋 방지시설 종합 분석")

    if has_process_emission:
        pdf.draw_sub_header("3) 공정배출시설 측정 결과 (냉각탑 TOC, 열교환기 등)")
        try: process_emission_data.sort(key=lambda x: str(x.get("period", "")))
        except: pass
        proc_rows = [[p.get("period","-"), p.get("date","-"), p.get("facility","-"), p.get("value","-"), p.get("limit", "-"), p.get("accuracy_check","-"), p.get("result","-")] for p in process_emission_data]
        pdf.draw_grouped_table(["구분(반기)", "측정일", "공정시설명", "측정결과", "기준", "증빙", "판정"], proc_rows, [30, 25, 55, 25, 20, 15, 20], highlight_last_col=True)

    pdf.draw_sub_header(f"{ldar_idx}) 비산누출시설 LDAR 점검 실적")
    ldar      = data.get("ldar", {})
    ldar_rows = [[d.get("year","-"), d.get("target_count","-"), d.get("leak_count","-"), d.get("leak_rate","-"), d.get("recheck_done","-"), d.get("result","-")] for d in ldar.get("data", [])]
    pdf.draw_zebra_table(["점검 연도", "전체 대상 개소", "누출 초과 수", "누출률", "재측정/조치 완료", "최종 판정"], ldar_rows, [25, 30, 25, 25, 50, 35], highlight_last_col=True)
    if ldar.get("analysis"): pdf.draw_text_box(ldar["analysis"], title="📋 LDAR 종합 분석")

    pdf.draw_section_header("마. 위험도 매트릭스 및 행정처분 가능성 평가")
    pdf.draw_sub_header("1) 항목별 위험도 평가")
    risk_items = data.get("risk_matrix", [{"item": "방지시설 농도 초과", "probability": "낮음", "impact": "높음", "priority": "High"}, {"item": "LDAR 기록 누락", "probability": "중간", "impact": "중간", "priority": "Medium"}])
    pdf.draw_zebra_table(["위험 항목", "발생 가능성", "영향도", "우선순위"], [[r.get("item","-"), r.get("probability","-"), r.get("impact","-"), r.get("priority","-")] for r in risk_items], [82, 36, 36, 36], highlight_last_col=True)

    legend_text = "※ 위험도 기준\n  High(높음)   : 즉시 조치 필요. 미이행 시 조업정지 또는 고발 가능성 높음\n  Medium(중간) : 3개월 이내 개선 권고. 반복 위반 시 행정처분 이력 가중\n  Low(낮음)    : 6개월 이내 자율 개선. 정기 점검 시 지적 가능성 있음"
    pdf.draw_text_box(legend_text)

    pdf.draw_sub_header("2) 현 관리 수준 기준 행정처분 예상 시나리오")
    scenario_rows = [
        ["농도 기준 초과 1회",  "경고(서면)",     "2주 이내", "방지시설 즉시 점검 및 재측정 결과 제출"],
        ["농도 기준 초과 2회",  "조업정지 10일",  "1개월",    "시설 교체 또는 처리효율 개선 계획서 제출"],
        ["LDAR 점검 미실시",   "과태료 200만원", "즉시",     "점검 이행 후 결과보고서 제출"],
        ["보고서 미제출",      "과태료 300만원", "즉시",     "지연 제출 시 가중 처벌 가능"],
        ["관리담당자 미선임",  "과태료 200만원", "즉시",     "선임 후 신고서 즉시 제출"],
    ]
    pdf.draw_zebra_table(["위반 내역", "예상 처분", "처리 기한", "대응 방안"], scenario_rows, [45, 35, 25, 85])

    pdf.draw_section_header("바. AI 정밀 진단 종합 의견 및 중장기 로드맵")
    pdf.draw_sub_header("1) 중장기 개선 로드맵")
    roadmap = data.get("improvement_roadmap", [
        {"phase": "단기(~6개월)", "action": "방지시설 처리효율 점검", "expected_effect": "농도 저감"},
    ])
    pdf.draw_zebra_table(["단계/기간", "주요 개선 조치", "기대 효과"], [[r.get("phase","-"), r.get("action","-"), r.get("expected_effect","-")] for r in roadmap], [38, 92, 60])

    pdf.draw_sub_header("2) AI 정밀 진단 종합 의견")
    op = data.get("overall_opinion", "AI 분석 내용을 가져오지 못했습니다.")
    pdf.draw_text_box(op)

   # ---------------------------------------------------------
    # 사. 관련 규제 및 행정처분 참고사항 (텍스트 표 대신 이미지 고정 삽입)
    # ---------------------------------------------------------
    pdf.add_page()
    pdf.draw_section_header("사. 관련 규제 및 행정처분 참고사항")
    pdf.ln(5)
    
    # 1. 행정처분 규정 표 이미지 삽입
    fn = pdf._fn()
    try:
        # x=10(좌측 여백), w=190(용지 폭에 맞춤)
        pdf.image("assets/penalty_table.png", x=10, w=190)
    except Exception:
        pdf.set_font(fn, "", 10); pdf.set_text_color(200, 0, 0)
        pdf.draw_text_box("[이미지 로드 실패: assets/penalty_table.png 파일을 확인하세요]")
    
    pdf.ln(15)

    # ---------------------------------------------------------
    # 아. 비산배출시설 변경신고 및 추진체계 (새로 추가된 항목)
    # ---------------------------------------------------------
    pdf.draw_section_header("아. 비산배출시설 변경신고 및 추진체계")
    pdf.ln(5)
    
    # 2. 변경신고 이미지 삽입
    try:
        pdf.image("assets/change_report.jpg", x=10, w=190)
    except Exception:
        pdf.draw_text_box("[이미지 로드 실패: assets/change_report.jpg]")
        
    pdf.ln(10)
    
    # 3. 추진체계 이미지 삽입
    try:
        pdf.image("assets/system_flow.jpg", x=10, w=190)
    except Exception:
        pdf.draw_text_box("[이미지 로드 실패: assets/system_flow.jpg]")

    pdf.ln(10)

    # ---------------------------------------------------------
    # 자. 자가 체크리스트 (정기 점검표) - 기존 '아'에서 '자'로 변경
    # ---------------------------------------------------------
    pdf.add_page()
    pdf.draw_section_header("자. 자가 체크리스트 (정기 점검표)")
    pdf.draw_sub_header("□ 비산배출시설 일상 점검 체크리스트")
    checklist = [
        ("일일", "방지시설 가동 상태 확인 및 이상 유무 기록"),
        ("일일", "국소배기장치 팬 가동 여부 점검 및 덕트 연결부 육안 확인"),
        ("주간", "방지시설 차압계 수치 기록 및 설계 범위 이탈 여부 확인"),
        ("월간", "활성탄 흡착제 잔여 수명 평가 및 교체 계획 수립"),
        ("반기", "방지시설 처리효율 측정 및 농도 기록 (정기점검보고서 기재)"),
        ("반기", "LDAR 정기 점검 실시 및 누출 수·재측정 결과 보고서 작성"),
        ("연간", "정기점검보고서 지방환경청 제출 (기한: 반기 종료 후 30일 이내)"),
    ]
    pdf.draw_zebra_table(["확인", "점검 주기", "점검 항목"], [["□", period, content] for period, content in checklist], [15, 25, 150])
    pdf.ln(4)

    pdf.set_font(fn, "B", 9); pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 7, "■ 점검 확인 서명란", 0, 1, "L"); pdf.ln(1)
    
    sign_y = pdf.get_y()
    pdf.set_draw_color(160, 175, 200); pdf.set_line_width(0.35)
    for i, label in enumerate(["작성자", "검토자", "승인자(대표)"]):
        bx = 10 + i * 62
        pdf.rect(bx, sign_y, 60, 26, "D")
        pdf.set_font(fn, "B", 8); pdf.set_text_color(85, 100, 125); pdf.set_xy(bx, sign_y + 2); pdf.cell(60, 5, label, 0, 0, "C")
        pdf.set_font(fn, "", 8); pdf.set_xy(bx, sign_y + 9); pdf.cell(60, 5, "직위 :", 0, 0, "L")
        pdf.set_xy(bx, sign_y + 17); pdf.cell(60, 5, "서명 :", 0, 0, "L")

    return bytes(pdf.output())
