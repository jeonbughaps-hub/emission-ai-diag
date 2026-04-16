import os
import fitz
from google import genai
from google.genai import types
from PIL import Image
import io
import json
import re
import streamlit as st
from datetime import datetime
import gc 
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

def extract_pdfs_from_source(uploaded_files):
    pdf_list = []
    if not uploaded_files: return pdf_list
    if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
    for uf in uploaded_files:
        if uf.name.lower().endswith(".pdf"):
            pdf_list.append((uf.name, uf))
    return pdf_list

def convert_and_mask_images(pdf_list):
    all_images = []
    my_bar = st.progress(0.1, text="PDF 문서 정밀 스캔 중...")
    for idx, (name, fbytes) in enumerate(pdf_list):
        try:
            fbytes.seek(0)
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 75)))
                if img.mode != 'RGB': img = img.convert('RGB')
                all_images.append(img)
                del pix
            doc.close()
        except Exception: continue
    gc.collect()
    my_bar.empty()
    return all_images

def analyze_log_compliance(measure_images, user_industry: str, vector_db):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not measure_images: return {"parsed": {}, "raw": ""}
    client = genai.Client(api_key=api_key)
    
    industry_str = str(user_industry).upper()
    if any(x in industry_str for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]):
        limit_val = 100
        limit_text = "100ppm"
    else:
        limit_val = 50
        limit_text = "50ppm"
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    prompt = f"""당신은 환경부 비산배출시설 기술진단 전문 엔진입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[★ 최우선 지시사항 : 데이터 전수 추출 ★]
1. 데이터 누락 불가: 첨부된 문서에 기록된 모든 연도(2년이든 3년이든 전체)의 방지시설 농도와 LDAR 데이터를 단 하나도 빠짐없이 JSON에 배열로 추출하세요.

[전문 종합 의견 작성 지침]
- 아래 4가지 소제목을 사용하여 800자 내외로 상세하게 작성하세요.
   【1. 시설관리 종합 평가】, 【2. 방지시설 효율성 분석】, 【3. LDAR 점검 이행 평가】, 【4. 중장기 관리 권고 사항】

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"B"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "추출날짜", "facility": "추출시설명", "value": "추출농도", "limit": "{limit_text}", "result": "적합/부적합"}} ] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "135", "leak_count": "0", "leak_rate": "0%", "recheck_done": "이행완료", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "시설관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검 강화", "expected_effect": "효율 안정화"}} ],
  "overall_opinion": "여기에 소제목을 포함하여 상세히 작성하세요."
}}
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt] + measure_images,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1, 
                max_output_tokens=8192, 
                safety_settings=[types.SafetySetting(category=c, threshold="BLOCK_NONE") for c in ["HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
            )
        )
        raw_text = response.text.strip()
        parsed_data = json.loads(re.search(r'\{.*\}', raw_text, re.DOTALL).group(0), strict=False)
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}

# ★ 대기질 데이터를 활용하여 VOCs 연계 전문가 제언을 생성하는 함수 ★
def generate_advanced_air_advice(station_name: str, pm10_val: str, o3_val: str):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key: return "대기질 정보를 불러올 수 없습니다."
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
당신은 대기환경 전문 연구원입니다.
관할 측정소({station_name})의 현재 실시간 대기질은 미세먼지(PM10): {pm10_val} ㎍/m³, 오존(O3): {o3_val} ppm 입니다.
이 사업장은 인쇄, 코팅 등에서 '유기용제(VOCs)'를 다량 취급하는 비산배출시설입니다.

아래 3가지 소제목을 사용하여 500자 분량의 아주 깊이 있고 전문적인 '환경 관리 지침'을 작성하세요.
반드시 '광화학 반응', '2차 생성 미세먼지', '오존 생성 전구물질' 등의 전문 학술 용어를 자연스럽게 포함하세요.

【1. 지역 대기질 현황 및 화학적 연관성】
- 현재 지역의 오존/미세먼지 수치를 언급하며, 사업장에서 배출되는 유기용제(VOCs)가 질소산화물(NOx)과 태양광 아래서 광화학 반응을 일으켜 오존(O3)을 생성하고, 2차 유기 에어로졸로 변환되어 미세먼지를 가중시킨다는 점을 과학적으로 설명.

【2. 현장 비산배출원 선제적 통제 가이드】
- 오후 피크타임(14~16시) 유기용제 고농도 작업 조정 권고 및 옥외 하역, 이송, 혼합 과정에서의 원천적 누출 차단 관리 방안 제시.

【3. 방지시설 및 LDAR 연계 집중 관리】
- 활성탄 흡착탑 등 대기오염 방지시설의 처리 효율 최적화 방안 및 회전/연결 기기(플랜지, 밸브)에 대한 선제적 LDAR(누출탐지 및 보수) 강화 지시.
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0.3)
        )
        return response.text.strip()
    except Exception:
        return "대기질 API 연동 지연으로 상세 분석을 생략합니다. 사업장 자체적인 VOCs 누출 점검을 강화해 주시기 바랍니다."

def build_vector_db(uploaded_files=None, location_key="default"):
    return None
