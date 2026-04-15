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

# ImportError 방지를 위한 안전한 임포트
try:
    import utils
except ImportError:
    utils = None

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
    my_bar = st.progress(0.1, text="PDF 문서 이미지 변환 중...")
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
    
    # ★ 업종 기준 명확화: Ⅲ/Ⅳ업종 = 100ppm
    industry_str = str(user_industry).upper()
    if any(x in industry_str for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]):
        limit_val = 100
        limit_text = "100ppm"
    else:
        limit_val = 50
        limit_text = "50ppm"
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ★ 보고서 생성기(pdf_generator)와 키값(Key)을 완벽히 일치시킨 프롬프트
    prompt = f"""당신은 환경부 비산배출시설 전문 진단 엔진입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[데이터 추출 및 보고서 매핑 규칙]
1. 방지시설 농도 판정: 측정 농도가 {limit_val}ppm을 초과하면 "부적합", 이하이면 "적합"으로 판정하세요.
2. 수치 데이터 강제 추출: 문서 내 표에서 '측정값(숫자)'을 반드시 찾아내어 'value' 필드에 넣으세요.
3. 보고서 출력 보장: 아래 JSON 구조의 키값(facility, value, target_count 등)을 절대 변경하지 마세요.

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "2022", "name": "이름", "dept": "부서", "date": "날짜", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "날짜", "facility": "시설명", "value": "측정수치", "limit": "{limit_text}", "result": "적합/부적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "2022", "target_count": "총개소", "leak_count": "누출수", "leak_rate": "0%", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "시설관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "점검이행", "expected_effect": "강화"}} ],
  "overall_opinion": "종합 진단 의견을 상세히 작성하세요."
}}
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt] + measure_images,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                safety_settings=[types.SafetySetting(category=c, threshold="BLOCK_NONE") for c in ["HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
            )
        )
        raw_text = response.text.strip()
        parsed_data = json.loads(re.search(r'\{.*\}', raw_text, re.DOTALL).group(0), strict=False)
        
        # 데이터가 없을 경우를 대비한 방어 로직 (보고서 빈칸 방지)
        if not parsed_data.get("prevention", {}).get("data"):
            parsed_data["prevention"] = {"data": [{"period": "-", "date": "-", "facility": "데이터 없음", "value": "-", "limit": limit_text, "result": "-"}]}
            
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}

# 기존에 누락되었던 build_vector_db 함수 추가 (ImportError 해결)
def build_vector_db(uploaded_files=None, location_key="default"):
    return None
