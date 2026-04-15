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

[중요 지시: 전문 종합 의견(overall_opinion) 작성 지침]
- 보고서의 품격을 위해 아래 4가지 소제목을 사용하여 800자 내외로 상세히 작성하세요.
- 단순 나열이 아닌 데이터에 기반한 기술적 분석을 수행하세요.

【1. 시설관리 종합 평가】: 전반적인 법규 준수 수준과 등급 산정 근거 요약.
【2. 방지시설 효율성 분석】: THC 농도 변화와 기준치({limit_text}) 대비 안정적 운영 여부 진단.
【3. LDAR 점검 이행 평가】: 누출률 관리 상태 및 점검 기록의 충실도 분석.
【4. 중장기 관리 권고 사항】: 정기점검 및 환경청 지도점검 대비 핵심 이행 과제 제언.

[출력 JSON 구조]
{{
  "scores": {{ 
    "manager_score": {{"score":100, "grade":"A", "reason":"적정"}}, 
    "prevention_score": {{"score":95, "grade":"A", "reason":"준수"}}, 
    "ldar_score": {{"score":100, "grade":"A", "reason":"양호"}}, 
    "record_score": {{"score":90, "grade":"B", "reason":"보통"}}, 
    "overall_score": {{"score":96, "grade":"A"}} 
  }},
  "manager": {{ "data": [ {{"period": "2022", "name": "마스킹됨", "dept": "안전", "date": "선임일", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "날짜", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "accuracy_check": "확인됨", "result": "판정"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "2022", "target_count": "총수", "leak_count": "누출수", "leak_rate": "0%", "recheck_done": "이행완료", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "시설관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검", "expected_effect": "안정화"}} ],
  "overall_opinion": "여기에 위 4가지 소제목을 포함하여 상세히 작성하세요."
}}
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt] + measure_images,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
                safety_settings=[types.SafetySetting(category=c, threshold="BLOCK_NONE") for c in ["HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
            )
        )
        raw_text = response.text.strip()
        parsed_data = json.loads(re.search(r'\{.*\}', raw_text, re.DOTALL).group(0), strict=False)
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}

def build_vector_db(uploaded_files=None, location_key="default"):
    return None
