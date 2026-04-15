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
    
    # Ⅲ/Ⅳ업종 기준 100ppm 반영
    industry_str = str(user_industry).upper()
    if any(x in industry_str for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]):
        limit_val = 100
        limit_text = "100ppm"
    else:
        limit_val = 50
        limit_text = "50ppm"
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    prompt = f"""당신은 환경부 비산배출시설 정밀 진단 시스템의 핵심 AI 엔진입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[진단 지시사항 - 풍부한 의견 중심]
1. 데이터 추출: '방지시설 농도', 'LDAR 합계'를 정확히 추출하고, 기준치({limit_val}ppm) 초과 여부를 정밀 판정하세요.
2. 종합 의견(overall_opinion) 생성: 
   - 문장 도입부에 현재 사업장의 전반적인 관리 등급을 명시하세요.
   - 방지시설의 THC 농도 추이가 기준 이내인지, 혹은 특정 시설에서 왜 농도가 높게 나왔는지(이미지 분석 근거) 상세히 설명하세요.
   - LDAR 누출률과 재측정 이행 상태를 평가하고, 다음 정기점검 시 주의해야 할 행정처분 위험 요소를 구체적으로(예: 3년 주기 정기점검 대비 등) 500자 이상 풍부하게 작성하세요.
3. 로드맵: 단기(~3개월) 및 중장기(~1년) 개선 조치를 사업장의 실정에 맞게 구체화하세요.

[출력 JSON 구조 - pdf_generator 연동용]
{{
  "scores": {{ 
    "manager_score": {{"score":100, "grade":"A", "reason":"선임 및 교육 이수 확인"}}, 
    "prevention_score": {{"score":95, "grade":"A", "reason":"농도 기준 준수 상태 양호"}}, 
    "ldar_score": {{"score":100, "grade":"A", "reason":"전수 점검 및 누출 0건"}}, 
    "record_score": {{"score":90, "grade":"B", "reason":"운영기록부 서식 보완 필요"}}, 
    "overall_score": {{"score":96, "grade":"A"}} 
  }},
  "manager": {{ "data": [ {{"period": "2022", "name": "이름", "dept": "부서", "date": "날짜", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "날짜", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "accuracy_check": "확인됨", "result": "판정"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "2022", "target_count": "총수", "leak_count": "누출수", "leak_rate": "0%", "recheck_done": "이행완료", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "시설 노후화", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기(~3M)", "action": "방지시설 활성탄 교체", "expected_effect": "배출 농도 안정화"}} ],
  "overall_opinion": "여기에 환경 전문가 수준의 풍부한 진단 의견을 작성하세요."
}}
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt] + measure_images,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2, # 의견 풍부화를 위해 약간의 창의성 허용
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
