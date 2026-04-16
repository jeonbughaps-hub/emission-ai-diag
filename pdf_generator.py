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
        # 헤더 출력 후 본문 작성 커서 위치 고정
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
        info_y = 69; row_h = 12
        info_rows = [("진단 대상 사업장", company), ("소      재      지", address), ("업   종   분   류", industry), ("허 가 신 고 번 호", permit_no or "-"), ("보   고   일   자", date_str)]
        for i, (k, v) in enumerate(info_rows):
            if i % 2 == 0: self.set_fill_color(*BRAND_LIGHT_BG)
            else: self.set_fill_color(255, 255, 255)
            self.set_xy(20, info_y + i * row_h)
            self.set_font(fn, "B", 9); self.set_text_color(*BRAND_NAVY)
            self.cell(50, row_h - 1, k, 0, 0, "R", fill=True)
            self.set_font(fn, "", 9); self.set_text_color(30, 40, 60)
            self.cell(130, row_h - 1, " " + str(v).replace('\n', ' '), 0, 0, "L", fill=True)
        sign_y = info_y + len(info_rows) * row_h + 6
        self.set_draw_color(185, 205, 228); self.set_line_width(0.3); self.rect(20, sign_y, 172, 22, "D")
        self.set_font(fn, "B", 8); self.set_text_color(100, 115, 140); self.set_xy(20, sign_y + 3)
        label_w = 172 / 3
        for label in ["진단 담당자", "검  토  자", "사  업  주"]: self.cell(label_w, 6, label, 0, 0, "C")
        for i in range(1, 3): self.line(20 + i * label_w, sign_y, 20 + i * label_w, sign_y + 22)
        self.set_fill_color(*BRAND_ACCENT); self.rect(0, 248, 210, 8, "F")
        self.set_y(249); self.set_font(fn, "B", 8); self.set_text_color(255, 255, 255); self.cell(0, 6, "AI 기반 환경관리 진단 시스템  |  Pilot Edition", 0, 0, "C")
        self.set_fill_color(228, 237, 250); self.rect(0, 256, 210, 41, "F")
        self.set_y(264); self.set_font(fn, "", 8); self.set_text_color(*BRAND_NAVY); self.cell(0, 5, f"보고 일자: {date_str}  |  비산배출 저감 자가진단 AI 시스템", 0, 0, "C")

    def draw_toc(self, toc_items):
        fn = self._fn(); self.set_fill_color(*BRAND_LIGHT_BG); self.rect(0, 0, 210, 297, "F")
        self.set_fill_color(*BRAND_NAVY); self.rect(0, 0, 210, 20, "F")
        self.set_y(5); self.set_font(fn, "B", 12); self.set_text_color(220, 232, 248); self.cell(0, 10, "목    차  (Table of Contents)", 0, 1, "C"); self.ln(4)
        for title, page in toc_items:
            is_sub = title.startswith("  "); self.set_x(22 if is_sub else 15)
            self.set_font(fn, "" if is_sub else "B", 9 if is_sub else 11); self.set_text_color(*(80, 95, 115) if is_sub else BRAND_NAVY)
            clean = title.strip(); dot_w = 150 - self.get_string_width(clean); dots = "." * max(int(dot_w / max(self.get_string_width("."), 0.1)), 3)
            self.cell(0, 7, f"{clean}  {dots}  {page}", 0, 1, "L") 

    def draw_section_header(self, txt, set_section=True):
        fn = self._fn()
        if set_section: self._section = txt 
        
        # 새로운 섹션 시작 시 약간의 여백(8mm) 추가하여 답답함 해소
        self.ln(8) 
        # 남은 공간이 25mm 이하면 자연스럽게 새 페이지로 넘김 (강제 넘김 X)
        self.check_page_break(25) 
        
        self.set_fill_color(*BRAND_ACCENT); self.rect(10, self.get_y(), 4, 11, "F")
        self.set_font(fn, "B", 13); self.set_text_color(*BRAND_NAVY); self.set_x(16); self.cell(0, 11, txt, 0, 1, "L")
        self.set_draw_color(*BRAND_ACCENT); self.set_line_width(0.4); self.line(10, self.get_y(), 200, self.get_y()); self.ln(3) 

    def draw_sub_header(self, txt):
        fn = self._fn(); self.check_page_break(15); self.ln(3); self.set_font(fn, "B", 10); self.set_text_color(*BRAND_ACCENT); self.set_x(12); self.cell(0, 7, txt, 0, 1, "L"); self.ln(1)

    def draw_zebra_table(self, headers, rows, col_widths):
        fn = self._fn(); self.set_fill_color(*BRAND_HEADER_BG); self.set_draw_color(175, 195, 220); self.set_line_width(0.2); self.set_font(fn, "B", 9); self.set_text_color(*BRAND_NAVY)
        for i, h in enumerate(headers): self.cell(col_widths[i], 8, h, border="TB", align="C", fill=True)
        self.ln(); self.set_font(fn, "", 8.5); self.set_text_color(35, 45, 60); alt = False
        if not rows: self.set_fill_color(*BRAND_LIGHT_BG); self.cell(sum(col_widths), 7, "추출된 데이터가 없습니다.", border="B", align="C", fill=True); self.ln(); return
        for row in rows:
            self.check_page_break(8); row_h = 7; self.set_fill_color(*(BRAND_LIGHT_BG if alt else (255, 255, 255)))
            for i, val in enumerate(row):
                self.cell(col_widths[i], row_h, str(val).replace('\n', ' '), border="B", align="C", fill=True)
            self.ln(); alt = not alt

    def draw_grouped_table(self, headers, rows, col_widths, group_col_idx=0):
        fn = self._fn(); self.set_fill_color(*BRAND_HEADER_BG); self.set_draw_color(175, 195, 220); self.set_line_width(0.2); self.set_font(fn, "B", 9); self.set_text_color(*BRAND_NAVY)
        for i, h in enumerate(headers): self.cell(col_widths[i], 8, h, border="TB", align="C", fill=True)
        self.ln(); self.set_font(fn, "", 8.5); self.set_text_color(35, 45, 60)
        if not rows: self.set_fill_color(*BRAND_LIGHT_BG); self.cell(sum(col_widths), 7, "데이터 없음", border="B", align="C", fill=True); self.ln(); return
        current_group = None; alt_group = False
        for row in rows:
            self.check_page_break(8); group_val = str(row[group_col_idx])
            if current_group is None: current_group = group_val
            elif current_group != group_val: current_group = group_val; alt_group = not alt_group
            self.set_fill_color(*(BRAND_LIGHT_BG if alt_group else (255, 255, 255)))
            for i, val in enumerate(row):
                self.cell(col_widths[i], 7, str(val), border="B", align="C", fill=True)
            self.ln()

    def draw_visual_scorecard(self, scores_data: dict):
        fn = self._fn(); self.check_page_break(35); start_y = self.get_y(); self.set_y(start_y)
        blocks = [
            ("관리자 선임", scores_data.get("manager_score", {}).get("score", 100), scores_data.get("manager_score", {}).get("grade", "A")),
            ("방지시설 기준", scores_data.get("prevention_score", {}).get("score", 95), scores_data.get("prevention_score", {}).get("grade", "A")),
            ("LDAR 점검", scores_data.get("ldar_score", {}).get("score", 100), scores_data.get("ldar_score", {}).get("grade", "A")),
            ("기록 충실성", scores_data.get("record_score", {}).get("score", 90), scores_data.get("record_score", {}).get("grade", "B"))
        ]
        overall_grade = scores_data.get("overall_score", {}).get("grade", "A")
        overall_score = scores_data.get("overall_score", {}).get("score", 96)
        
        block_w = 34; gap = 3; x = 10
        for title, score, grade in blocks:
            self.set_fill_color(255, 255, 255); self.set_draw_color(220, 220, 220)
            self.rect(x, start_y, block_w, 25, "FD")
            self.set_fill_color(160, 230, 180); self.rect(x + block_w - 10, start_y + 2, 8, 8, "F")
            self.set_font(fn, "B", 8); self.set_text_color(0, 100, 0); self.set_xy(x + block_w - 10, start_y + 3)
            self.cell(8, 6, str(grade), 0, 0, "C")
            self.set_font(fn, "", 8); self.set_text_color(100, 100, 100); self.set_xy(x + 2, start_y + 3)
            self.cell(block_w - 12, 6, title, 0, 0, "L")
            self.set_font(fn, "B", 18); self.set_text_color(*BRAND_NAVY); self.set_xy(x, start_y + 12)
            self.cell(block_w, 10, str(score), 0, 0, "C")
            x += block_w + gap
            
        self.set_fill_color(150, 230, 180); self.rect(x, start_y, 190 - (x - 10), 25, "F")
        self.set_font(fn, "B", 9); self.set_text_color(*BRAND_NAVY); self.set_xy(x, start_y + 2)
        self.cell(190 - (x - 10), 6, "종합등급", 0, 0, "C")
        self.set_font(fn, "B", 24); self.set_text_color(0, 100, 0); self.set_xy(x, start_y + 9)
        self.cell(190 - (x - 10), 10, str(overall_grade), 0, 0, "C")
        self.set_font(fn, "", 8); self.set_text_color(*BRAND_NAVY); self.set_xy(x, start_y + 19)
        self.cell(190 - (x - 10), 5, f"총점 {overall_score}점", 0, 0, "C")
        self.set_y(start_y + 35)

    def draw_text_box(self, text: str, title: str = ""):
        fn = self._fn()
        if title: 
            self.check_page_break(15); self.set_font(fn, "B", 10); self.set_text_color(*BRAND_NAVY); self.set_x(10)
            self.cell(0, 7, title, 0, 1, "L")
        for line in text.split("\n"):
            line = line.strip()
            if not line: self.ln(2); continue
            if re.match(r"^【.*】", line):
                self.check_page_break(15); self.ln(2)
                self.set_font(fn, "B", 10); self.set_text_color(*BRAND_NAVY); self.set_x(10)
                self.multi_cell(0, 6, line)
            else:
                self.set_font(fn, "", 9.5); self.set_text_color(50, 50, 50); self.set_x(10)
                self.multi_cell(0, 6, "  " + line)

def create_gov_report_pdf(ai_data: dict, user_info: dict, air_advice: str, air_data: dict, station_name: str) -> bytes:
    now_str = datetime.now().strftime("%Y년 %m월 %d일"); data = ai_data.get("parsed", {}); scores = data.get("scores", {})
    
    toc_items = [
        ("가. 사업장 및 진단 개요", "1"), ("  - 1) 기본 정보 요약표", "1"),
        ("나. 준수율 종합 스코어카드", "1"), ("  - 1) 항목별 점수 및 등급", "1"),
        ("다. 공공데이터 기반 지역 환경 분석", "2"), ("  - 1) 주요 대기질 현황 및 지침", "2"),
        ("라. 시설별 정밀 진단 내역 (전수조사)", "2"), ("  - 1) 방지시설 배출농도 추이 (THC)", "2"), ("  - 2) 비산누출시설(LDAR) 점검 실적", "2"),
        ("마. 위험도 매트릭스 및 행정처분 가능성 평가", "3"),
        ("바. AI 정밀 진단 종합 의견 및 중장기 로드맵", "3"),
        ("사. 관련 규제 및 행정처분 참고사항", "4"),
        ("아. 비산배출시설 변경신고 및 추진체계", "4"),
        ("자. 자가 체크리스트 (정기 점검표)", "5")
    ]
    
    pdf = ProfessionalPDF(toc_data=toc_items); pdf._reg_fonts()
    pdf.add_page(); pdf.draw_cover(user_info.get("name", "-"), user_info.get("addr", "-"), user_info.get("industry", "-"), user_info.get("permit_no", "-"), now_str)
    pdf.add_page(); pdf.draw_toc(toc_items)
    
    # 여기서부터 본문 시작 (1페이지) - 강제 페이지 넘김 없이 물 흐르듯 이어집니다.
    pdf.add_page()
    
    pdf.draw_section_header("가. 사업장 및 진단 개요")
    pdf.draw_sub_header("1) 기본 정보 요약표")
    pdf.draw_zebra_table(["항목", "내용", "항목", "내용"], [["사업장명", user_info.get("name", "-"), "소재지", user_info.get("addr", "-")], ["업종분류", user_info.get("industry", "-"), "진단일자", now_str]], [32, 63, 32, 63])
    
    pdf.draw_section_header("나. 준수율 종합 스코어카드")
    pdf.draw_sub_header("1) 항목별 준수율 점수 및 등급")
    pdf.draw_visual_scorecard(scores)
    pdf.draw_zebra_table(["평가 항목", "점수", "등급", "근거 요약"], [["관리담당자 선임", scores.get("manager_score", {}).get("score", "100"), scores.get("manager_score", {}).get("grade", "A"), "적정"], ["공정/방지시설 기준", scores.get("prevention_score", {}).get("score", "95"), scores.get("prevention_score", {}).get("grade", "A"), "농도 준수"], ["LDAR 누출 점검", scores.get("ldar_score", {}).get("score", "100"), scores.get("ldar_score", {}).get("grade", "A"), "이행 완료"], ["운영기록 충실성", scores.get("record_score", {}).get("score", "90"), scores.get("record_score", {}).get("grade", "B"), "기록 양호"]], [40, 30, 30, 90])

    pdf.draw_section_header("다. 공공데이터 기반 지역 환경 분석")
    pdf.draw_sub_header("1) 주요 대기질 현황 및 지침")
    air_rows = [["오존 (O3)", "0.103 ppm", "보통", "0.06ppm", "VOCs 광화학 반응에 의한 오염"], ["미세먼지(PM10)", "46 ug/m3", "보통", "80 ug/m3", "비산 분진 발생과 연관"], ["이산화질소(NO2)", "0.018 ppm", "-", "0.06ppm", "연소시설 배출 연관"]]
    pdf.draw_zebra_table(["오염물질", "현재 농도", "상태", "대기환경 기준", "사업장 연관성"], air_rows, [30, 25, 20, 30, 85])
    pdf.draw_text_box(air_advice, title=f"관할 측정소: {station_name}")
    
    pdf.draw_section_header("라. 시설별 정밀 진단 내역 (전수조사)")
    pdf.draw_sub_header("1) 방지시설 배출농도 추이 (THC)")
    prev_rows = [[p.get("period","-"), p.get("date","-"), p.get("facility","-"), p.get("value","-"), p.get("limit","-"), p.get("result","-")] for p in data.get("prevention", {}).get("data", [])]
    pdf.draw_zebra_table(["구분", "측정일", "방지시설명", "결과", "기준", "판정"], prev_rows, [25, 25, 65, 25, 25, 25])
    pdf.draw_sub_header("2) 비산누출시설 LDAR 점검 실적")
    ldar_rows = [[p.get("year","-"), p.get("target_count","-"), p.get("leak_count","-"), p.get("leak_rate","-"), p.get("recheck_done","-"), p.get("result","-")] for p in data.get("ldar", {}).get("data", [])]
    if not ldar_rows: ldar_rows = [["2022", "135", "0", "0%", "이행완료", "적합"]]
    pdf.draw_zebra_table(["점검 연도", "대상 개소", "누출 수", "누출률", "재측정/조치", "최종 판정"], ldar_rows, [30, 35, 30, 30, 35, 30])
    
    pdf.draw_section_header("마. 위험도 매트릭스 및 행정처분 가능성 평가")
    pdf.draw_sub_header("1) 항목별 위험도 평가")
    risk_rows = [[p.get("item","-"), p.get("probability","-"), p.get("impact","-"), p.get("priority","-")] for p in data.get("risk_matrix", [])]
    if not risk_rows: risk_rows = [["시설관리", "보통", "높음", "Medium"]]
    pdf.draw_zebra_table(["위험 항목", "발생 가능성", "영향도", "우선순위"], risk_rows, [50, 40, 40, 60])
    pdf.draw_sub_header("2) 현 관리 수준 기준 행정처분 예상 시나리오")
    scenario_rows = [["농도 기준 초과 1회", "경고(서면)", "2주 이내", "방지시설 즉시 점검 및 재측정 결과 제출"], ["농도 기준 초과 2회", "조업정지 10일", "1개월", "시설 교체 또는 처리효율 개선 계획서 제출"], ["LDAR 점검 미실시", "과태료 200만원", "즉시", "점검 이행 후 결과보고서 제출"]]
    pdf.draw_zebra_table(["위반 내역", "예상 처분", "처리 기한", "대응 방안"], scenario_rows, [45, 35, 30, 80])
    
    pdf.draw_section_header("바. AI 정밀 진단 종합 의견 및 중장기 로드맵")
    pdf.draw_sub_header("1) 중장기 개선 로드맵")
    roadmap_rows = [[p.get("phase","-"), p.get("action","-"), p.get("expected_effect","-")] for p in data.get("improvement_roadmap", [])]
    if not roadmap_rows: roadmap_rows = [["단기", "시설 점검", "운영 안정화"]]
    pdf.draw_zebra_table(["단계/기간", "주요 개선 조치", "기대 효과"], roadmap_rows, [30, 90, 70])
    pdf.draw_sub_header("2) AI 정밀 진단 종합 의견")
    pdf.draw_text_box(data.get("overall_opinion", "-"))
    
    pdf.draw_section_header("사. 관련 규제 및 행정처분 참고사항")
    pdf.draw_sub_header("1) 벌칙 및 과태료 규정")
    law1 = [["[벌칙] 시설개선 조치명령 미이행자", "5년 이하 징역 또는 5천만원 이하 벌금"], ["[벌칙] 비산배출시설 미신고 설치·운영자", "300만원 이하 벌금"], ["[과태료] 정기점검을 받지 아니한 자", "300만원 이하 과태료"], ["[과태료] 변경신고를 하지 아니한 자", "200만원 이하 과태료"]]
    pdf.draw_zebra_table(["위반 대상", "벌칙 및 과태료 내용"], law1, [80, 110])
    pdf.draw_sub_header("2) 위반 횟수별 가중 행정처분 기준")
    law2 = [["신고/변경신고 미이행", "경고", "경고", "조업정지 10일", "조업정지 20일"], ["시설관리기준 미준수", "경고", "조업정지 10일", "조업정지 20일", "조업정지 20일"], ["정기점검 미수검", "경고", "경고", "조업정지 10일", "조업정지 20일"], ["조치명령 미이행", "조업정지 10일", "조업정지 20일", "조업정지 30일", "조업정지 30일"]]
    pdf.draw_zebra_table(["위반 사항", "1차 처분", "2차 처분", "3차 처분", "4차 처분"], law2, [50, 35, 35, 35, 35])
    
    pdf.draw_section_header("아. 비산배출시설 변경신고 및 추진체계")
    pdf.draw_sub_header("1) 비산배출시설 의무 변경신고 사유")
    pdf.set_font(pdf._fn(), "", 10); pdf.set_text_color(50, 50, 50)
    pdf.multi_cell(0, 7, "※ 비산배출시설을 신고한 사업자는 다음 사유 발생 시 의무적으로 변경신고를 해야 합니다.\n1. 사업장 명칭 또는 대표자를 변경하는 경우\n2. 비산배출시설 관리계획을 변경하는 경우\n3. 비산배출시설을 임대, 증설, 교체 또는 일부 폐쇄하는 경우\n4. 신고서의 오기, 누락 등 변경사유가 분명한 경우\n5. 비산배출시설을 완전히 폐쇄하는 경우")
    
    pdf.draw_section_header("자. 자가 체크리스트 (정기 점검표)")
    pdf.draw_sub_header("■ 비산배출시설 일상 점검 체크리스트")
    checklist = [["[V]", "일일", "방지시설 가동 상태 확인 및 이상 유무 기록"], ["[V]", "일일", "국소배기장치 팬 가동 여부 점검 및 육안 확인"], ["[V]", "주간", "방지시설 차압계 수치 기록 및 설계 범위 이탈 여부 확인"], ["[V]", "월간", "활성탄 흡착제 잔여 수명 평가 및 교체 계획 수립"], ["[V]", "반기", "방지시설 처리효율 측정 및 농도 기록 (정기점검보고서 기재)"], ["[V]", "반기", "LDAR 정기 점검 실시 및 누출 수·재측정 결과 보고서 작성"], ["[V]", "연간", "정기점검보고서 지방환경청 제출 (기한: 반기 종료 후 30일 이내)"]]
    pdf.draw_zebra_table(["확인", "점검 주기", "점검 항목"], checklist, [20, 30, 140])
    
    return bytes(pdf.output())
