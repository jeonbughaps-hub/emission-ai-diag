import os
from fpdf import FPDF
from datetime import datetime
import re
from utils import FONT_FILE_NAME, FONT_BOLD_NAME, BRAND_NAVY, BRAND_ACCENT, BRAND_LIGHT_BG, BRAND_HEADER_BG, SCORE_COLORS, get_env_office, get_limit_ppm

def get_aqi_status(val, item_type):
    """수치에 따라 대기질 상태와 색상, 게이지 비율을 반환합니다."""
    try:
        v = float(val)
    except ValueError:
        return "정보없음", (150, 150, 150), 0
        
    if item_type == "PM10":
        if v <= 30: return "좋음", (50, 150, 255), min(v/150, 1.0)
        elif v <= 80: return "보통", (60, 180, 110), min(v/150, 1.0)
        elif v <= 150: return "나쁨", (240, 150, 50), min(v/150, 1.0)
        else: return "매우나쁨", (220, 60, 60), 1.0
    elif item_type == "O3":
        if v <= 0.030: return "좋음", (50, 150, 255), min(v/0.150, 1.0)
        elif v <= 0.090: return "보통", (60, 180, 110), min(v/0.150, 1.0)
        elif v <= 0.150: return "나쁨", (240, 150, 50), min(v/0.150, 1.0)
        else: return "매우나쁨", (220, 60, 60), 1.0
        
    return "측정불가", (150, 150, 150), 0

class ProfessionalPDF(FPDF):
    def __init__(self, toc_data=None):
        super().__init__()
        self._toc = toc_data or []
        self._section = ""
        self.set_auto_page_break(auto=True, margin=15) 
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
        self.set_xy(10, 7)
        self.cell(95, 5, "비산배출시설 정밀 자가진단 보고서", 0, 0, "L")
        self.set_x(10)
        self.cell(190, 5, getattr(self, '_section', ''), 0, 0, "R")
        self.set_draw_color(*BRAND_ACCENT)
        self.set_line_width(0.3)
        self.line(10, 13, 200, 13)
        self.set_xy(10, 18)

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
        
        info_y = 69
        row_h = 12
        info_rows = [
            ("진단 대상 사업장", company), 
            ("소      재      지", address), 
            ("업   종   분   류", industry), 
            ("허 가 신 고 번 호", permit_no or "-"), 
            ("보   고   일   자", date_str)
        ]
        
        for i, (k, v) in enumerate(info_rows):
            self.set_fill_color(*(BRAND_LIGHT_BG if i % 2 == 0 else (255, 255, 255)))
            self.set_xy(20, info_y + i * row_h)
            self.set_font(fn, "B", 9)
            self.set_text_color(*BRAND_NAVY)
            self.cell(50, row_h - 1, k, 0, 0, "R", fill=True)
            self.set_font(fn, "", 9)
            self.set_text_color(30, 40, 60)
            self.cell(130, row_h - 1, " " + str(v).replace('\n', ' '), 0, 0, "L", fill=True)
            
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
        for title, page in toc_items:
            is_sub = title.startswith("  ")
            self.set_x(22 if is_sub else 15)
            self.set_font(fn, "" if is_sub else "B", 9 if is_sub else 11)
            self.set_text_color(*(80, 95, 115) if is_sub else BRAND_NAVY)
            clean = title.strip()
            dot_w = 150 - self.get_string_width(clean)
            dots = "." * max(int(dot_w / max(self.get_string_width("."), 0.1)), 3)
            self.cell(0, 7, f"{clean}  {dots}  {page}", 0, 1, "L") 

    def draw_section_header(self, txt, set_section=True):
        fn = self._fn()
        if set_section: 
            self._section = txt 
        self.ln(8)
        self.check_page_break(25) 
        self.set_fill_color(*BRAND_ACCENT)
        self.rect(10, self.get_y(), 4, 11, "F")
        self.set_font(fn, "B", 13)
        self.set_text_color(*BRAND_NAVY)
        self.set_x(16)
        self.cell(0, 11, txt, 0, 1, "L")
        self.set_draw_color(*BRAND_ACCENT)
        self.set_line_width(0.4)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3) 

    def draw_sub_header(self, txt):
        fn = self._fn()
        self.check_page_break(15)
        self.ln(3)
        self.set_font(fn, "B", 10)
        self.set_text_color(*BRAND_ACCENT)
        self.set_x(12)
        self.cell(0, 7, txt, 0, 1, "L")
        self.ln(1)

    def draw_zebra_table(self, headers, rows, col_widths):
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
            self.set_fill_color(*(BRAND_LIGHT_BG if alt else (255, 255, 255)))
            for i, val in enumerate(row): 
                self.cell(col_widths[i], row_h, str(val).replace('\n', ' '), border="B", align="C", fill=True)
            self.ln()
            alt = not alt

    def draw_grouped_table(self, headers, rows, col_widths, group_col_idx=0):
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
            self.cell(sum(col_widths), 7, "데이터 없음", border="B", align="C", fill=True)
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
                
            self.set_fill_color(*(BRAND_LIGHT_BG if alt_group else (255, 255, 255)))
            for i, val in enumerate(row): 
                self.cell(col_widths[i], 7, str(val), border="B", align="C", fill=True)
            self.ln()

    def draw_visual_scorecard(self, scores_data: dict):
        fn = self._fn()
        self.check_page_break(35)
        start_y = self.get_y()
        self.set_y(start_y)
        
        blocks = [
            ("관리자 선임", scores_data.get("manager_score", {}).get("score", 100), scores_data.get("manager_score", {}).get("grade", "A")),
            ("방지시설 기준", scores_data.get("prevention_score", {}).get("score", 95), scores_data.get("prevention_score", {}).get("grade", "A")),
            ("LDAR 점검", scores_data.get("ldar_score", {}).get("score", 100), scores_data.get("ldar_score", {}).get("grade", "A")),
            ("기록 충실성", scores_data.get("record_score", {}).get("score", 90), scores_data.get("record_score", {}).get("grade", "B"))
        ]
        
        overall_grade = scores_data.get("overall_score", {}).get("grade", "A")
        overall_score = scores_data.get("overall_score", {}).get("score", 96)
        block_w = 34
        gap = 3
        x = 10
        
        for title, score, grade in blocks:
            self.set_fill_color(255, 255, 255)
            self.set_draw_color(220, 220, 220)
            self.rect(x, start_y, block_w, 25, "FD")
            
            self.set_fill_color(160, 230, 180)
            self.rect(x + block_w - 10, start_y + 2, 8, 8, "F")
            
            self.set_font(fn, "B", 8)
            self.set_text_color(0, 100, 0)
            self.set_xy(x + block_w - 10, start_y + 3)
            self.cell(8, 6, str(grade), 0, 0, "C")
            
            self.set_font(fn, "", 8)
            self.set_text_color(100, 100, 100)
            self.set_xy(x + 2, start_y + 3)
            self.cell(block_w - 12, 6, title, 0, 0, "L")
            
            self.set_font(fn, "B", 18)
            self.set_text_color(*BRAND_NAVY)
            self.set_xy(x, start_y + 12)
            self.cell(block_w, 10, str(score), 0, 0, "C")
            
            x += block_w + gap
            
        self.set_fill_color(150, 230, 180)
        self.rect(x, start_y, 190 - (x - 10), 25, "F")
        self.set_font(fn, "B", 9)
        self.set_text_color(*BRAND_NAVY)
        self.set_xy(x, start_y + 2)
        self.cell(190 - (x - 10), 6, "종합등급", 0, 0, "C")
        
        self.set_font(fn, "B", 24)
        self.set_text_color(0, 100, 0)
        self.set_xy(x, start_y + 9)
        self.cell(190 - (x - 10), 10, str(overall_grade), 0, 0, "C")
        
        self.set_font(fn, "", 8)
        self.set_text_color(*BRAND_NAVY)
        self.set_xy(x, start_y + 19)
        self.cell(190 - (x - 10), 5, f"총점 {overall_score}점", 0, 0, "C")
        
        self.set_y(start_y + 30)

    def draw_air_quality_infographic(self, station_name: str, air_data: dict):
        fn = self._fn()
        self.check_page_break(50)
        start_y = self.get_y()
        
        pm10_str = air_data.get("pm10Value", "-") if isinstance(air_data, dict) else "-"
        o3_str = air_data.get("o3Value", "-") if isinstance(air_data, dict) else "-"
        
        pm10_stat, pm10_color, pm10_ratio = get_aqi_status(pm10_str, "PM10")
        o3_stat, o3_color, o3_ratio = get_aqi_status(o3_str, "O3")

        self.set_fill_color(245, 248, 252)
        self.rect(10, start_y, 190, 46, "F")
        self.set_xy(15, start_y + 4)
        self.set_font(fn, "B", 10)
        self.set_text_color(*BRAND_NAVY)
        self.cell(0, 6, f"실시간 대기질 지수 현황 대시보드 (관할: {station_name})")

        # --- 1. 오존 (O3) 카드 ---
        self.set_fill_color(255, 255, 255)
        self.set_draw_color(210, 220, 230)
        self.rect(15, start_y + 13, 80, 28, "FD")
        
        self.set_xy(20, start_y + 16)
        self.set_font(fn, "B", 10)
        self.set_text_color(70, 80, 95)
        self.cell(30, 6, "오존 (O3)", 0, 0, "L")
        
        self.set_font(fn, "B", 15)
        self.set_text_color(40, 50, 60)
        self.set_xy(20, start_y + 23)
        self.cell(30, 8, f"{o3_str} ppm", 0, 0, "L")
        
        self.set_fill_color(*o3_color)
        self.rect(72, start_y + 16, 18, 6, "F")
        self.set_xy(72, start_y + 16.5)
        self.set_font(fn, "B", 9)
        self.set_text_color(255, 255, 255)
        self.cell(18, 5, o3_stat, 0, 0, "C")
        
        bar_w = 55
        bar_x = 20
        bar_y = start_y + 35
        self.set_fill_color(230, 235, 240)
        self.rect(bar_x, bar_y, bar_w, 3, "F")
        self.set_fill_color(*o3_color)
        self.rect(bar_x, bar_y, bar_w * o3_ratio, 3, "F")
        self.set_font(fn, "", 7)
        self.set_text_color(120, 120, 120)
        self.set_xy(bar_x + bar_w + 3, bar_y - 1.5)
        self.cell(10, 5, "기준: 0.09", 0, 0, "L")

        # --- 2. 미세먼지 (PM10) 카드 ---
        self.set_fill_color(255, 255, 255)
        self.set_draw_color(210, 220, 230)
        self.rect(105, start_y + 13, 80, 28, "FD")
        
        self.set_xy(110, start_y + 16)
        self.set_font(fn, "B", 10)
        self.set_text_color(70, 80, 95)
        self.cell(30, 6, "미세먼지 (PM10)", 0, 0, "L")
        
        self.set_font(fn, "B", 15)
        self.set_text_color(40, 50, 60)
        self.set_xy(110, start_y + 23)
        self.cell(30, 8, f"{pm10_str} ㎍/m³", 0, 0, "L")
        
        self.set_fill_color(*pm10_color)
        self.rect(162, start_y + 16, 18, 6, "F")
        self.set_xy(162, start_y + 16.5)
        self.set_font(fn, "B", 9)
        self.set_text_color(255, 255, 255)
        self.cell(18, 5, pm10_stat, 0, 0, "C")
        
        bar_w2 = 55
        bar_x2 = 110
        bar_y2 = start_y + 35
        self.set_fill_color(230, 235, 240)
        self.rect(bar_x2, bar_y2, bar_w2, 3, "F")
        self.set_fill_color(*pm10_color)
        self.rect(bar_x2, bar_y2, bar_w2 * pm10_ratio, 3, "F")
        self.set_font(fn, "", 7)
        self.set_text_color(120, 120, 120)
        self.set_xy(bar_x2 + bar_w2 + 3, bar_y2 - 1.5)
        self.cell(10, 5, "기준: 80", 0, 0, "L")

        self.set_y(start_y + 50)

    def draw_text_box(self, text: str, title: str = ""):
        fn = self._fn()
        if title: 
            self.check_page_break(15)
            self.set_font(fn, "B", 10)
            self.set_text_color(*BRAND_NAVY)
            self.set_x(10)
            self.cell(0, 7, title, 0, 1, "L")
            
        for line in text.split("\n"):
            line = line.strip()
            if not line: 
                self.ln(2)
                continue
                
            if re.match(r"^【.*】", line):
                self.check_page_break(15)
                self.ln(3)
                self.set_font(fn, "B", 10)
                self.set_text_color(*BRAND_NAVY)
                self.set_x(10)
                self.multi_cell(0, 6, line)
            else:
                self.set_font(fn, "", 9.5)
                self.set_text_color(50, 50, 50)
                self.set_x(10)
                self.multi_cell(0, 6, "  " + line)

def create_gov_report_pdf(ai_data: dict, user_info: dict, air_advice: str, air_data: dict, station_name: str) -> bytes:
    now_str = datetime.now().strftime("%Y년 %m월 %d일")
    data = ai_data.get("parsed", {})
    scores = data.get("scores", {})
    
    toc_items = [
        ("가. 사업장 및 진단 개요", "1"), 
        ("나. 준수율 종합 스코어카드", "1"), 
        ("다. 공공데이터 기반 지역 환경 분석", "2"), 
        ("라. 시설별 정밀 진단 내역 (전수조사)", "2"), 
        ("마. 위험도 매트릭스 및 행정처분 가능성 평가", "3"), 
        ("바. AI 정밀 진단 종합 의견 및 중장기 로드맵", "3"), 
        ("사. 관련 규제 및 행정처분 참고사항", "4"), 
        ("아. 비산배출시설 변경신고 및 추진체계", "4"), 
        ("자. 자가 체크리스트 (정기 점검표)", "5")
    ]
    
    pdf = ProfessionalPDF(toc_data=toc_items)
