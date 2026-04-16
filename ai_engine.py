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

# -------------------------------------------------------------------
# [업그레이드 1] 방지시설 및 LDAR 데이터 100% 전수조사 강제
# -------------------------------------------------------------------
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

    # ★ 강력한 전수 추출 명령 및 경고 추가 ★
    prompt = f"""당신은 환경부 비산배출시설 기술진단 전문 엔진입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[★ 최우선 지시사항 : 3개년치 데이터 100% 전수 추출 ★]
1. 데이터 누락 절대 금지: 첨부된 문서에 여러 해(최대 3년 이상)의 기록이 있습니다. 귀찮다고 1~2년치만 뽑고 멈추거나 요약하면 절대 안 됩니다. 
2. 방지시설 농도(prevention): 문서에 기록된 '모든 연도, 모든 반기, 모든 시설'의 측정 데이터를 단 1건도 빠짐없이 JSON 배열에 전부 담으세요. (데이터가 50개면 50개 모두 출력)
3. LDAR 점검(ldar): 문서에 기재된 '모든 연도'의 점검 개소와 누출 수를 연도별로 각각 분리하여 모두 추출하세요.

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
                temperature=0.1, # 일관성과 팩트 위주로 강제
                max_output_tokens=8192, # ★ 토큰 한계치를 최대로 늘려 중간에 멈추는 현상 방지
                safety_settings=[types.SafetySetting(category=c, threshold="BLOCK_NONE") for c in ["HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
            )
        )
        raw_text = response.text.strip()
        parsed_data = json.loads(re.search(r'\{.*\}', raw_text, re.DOTALL).group(0), strict=False)
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}

# -------------------------------------------------------------------
# [업그레이드 2] 유기물질(VOCs) 연계 대기질 전문 조언 생성기
# -------------------------------------------------------------------
def generate_advanced_air_advice(station_name: str, pm10_val: str, o3_val: str):
    """
    단순한 수치 안내를 넘어, VOCs(유기물질)가 오존 및 미세먼지에 
    미치는 광화학적 영향을 엮어 전문적인 조언을 생성합니다.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key: return "대기질 정보를 불러올 수 없습니다."
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
당신은 대기환경 전문가입니다.
관할 측정소({station_name})의 현재 대기질은 미세먼지(PM10): {pm10_val}, 오존(O3): {o3_val} 입니다.
보고서를 읽는 사업장은 '비산배출시설(유기물질, VOCs)'을 다량 취급하는 곳입니다.

다음 내용을 엮어서 전문적인 대기 환경 관리 지침(약 400자)을 3개의 항목으로 나누어 작성하세요.
1. 사업장에서 배출되는 유기물질(VOCs)이 태양빛과 반응해 '광화학 스모그'와 '오존(O3)'을 생성한다는 점.
2. 유기물질이 대기 중에서 2차 반응을 일으켜 '초미세먼지'를 가중시킨다는 점.
3. 따라서 현재 지역 대기질 수치를 고려할 때, 오후 피크타임 유기용제 사용 공정 단축, 활성탄 교체 주기 준수, LDAR 수시 점검 등을 어떻게 선제적으로 해야 하는지 조언.

[출력 형식 예시]
1. 현황 및 광화학적 영향: 지역 대기질(오존 {o3_val}, 미세먼지 {pm10_val})을 고려할 때... (VOCs 연계 설명)
2. 시설 운영 가이드: VOCs 배출에 의한 2차 오염(미세먼지 생성 등)을 막기 위해...
3. 선제적 저감 조치: 활성탄 교체 및...
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0.3)
        )
        return response.text.strip()
    except Exception:
        return "대기질 API 연동 지연으로 상세 분석을 생략합니다. 자체적인 VOCs 누출 점검을 강화해 주시기 바랍니다."

def build_vector_db(uploaded_files=None, location_key="default"):
    return None
