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

[★ 핵심 지시사항 ★]
1. 데이터 추출: 첨부된 '운영기록부' 이미지에서 **실제 데이터(측정일자, 시설명, 결과값)**를 반드시 추출하여 JSON 배열에 넣으세요. 귀찮다고 예시 데이터(예: "날짜", "시설명")를 그대로 출력하면 절대 안 됩니다!
2. 종합 의견 작성: 아래 4가지 소제목을 사용하여 800자 내외로 상세하고 전문적으로 작성하세요.

【1. 시설관리 종합 평가】
【2. 방지시설 효율성 분석】
【3. LDAR 점검 이행 평가】
【4. 중장기 관리 권고 사항】

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A", "reason":"적정"}}, "prevention_score": {{"score":95, "grade":"A", "reason":"준수"}}, "ldar_score": {{"score":100, "grade":"A", "reason":"양호"}}, "record_score": {{"score":90, "grade":"B", "reason":"보통"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "2022", "name": "실제이름", "dept": "실제부서", "date": "실제날짜", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "실제날짜", "facility": "실제시설명", "value": "실제농도", "limit": "{limit_text}", "accuracy_check": "확인됨", "result": "적합/부적합"}} ] }},
  "ldar": {{ "data": [ {{"year": "2022", "target_count": "135", "leak_count": "0", "leak_rate": "0%", "recheck_done": "이행완료", "result": "적합"}} ] }},
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
