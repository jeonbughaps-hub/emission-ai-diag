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
    my_bar = st.progress(0.1, text="PDF 문서 이미지 변환 및 최적화 중...")
    for idx, (name, fbytes) in enumerate(pdf_list):
        try:
            fbytes.seek(0)
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            for i, page in enumerate(doc):
                # 1.8배율 해상도 유지 및 75% 압축으로 대용량 대응
                pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 75)))
                if img.mode != 'RGB': img = img.convert('RGB')
                all_images.append(img)
                del pix
                if i % 5 == 0 or i == len(doc)-1:
                    my_bar.progress(0.1 + 0.8 * ((i+1)/len(doc)), text=f"[{name}] 스캔 중... ({i+1}/{len(doc)}장)")
            doc.close()
        except Exception: continue
    gc.collect()
    my_bar.empty()
    return all_images

def analyze_log_compliance(measure_images, user_industry: str, vector_db):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not measure_images: return {"parsed": {}, "raw": ""}
        
    client = genai.Client(api_key=api_key)
    
    # Ⅲ/Ⅳ업종 기준 100ppm 반영 로직
    industry_str = str(user_industry).upper()
    if any(x in industry_str for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]):
        limit_val = 100
        limit_text = "100ppm"
    else:
        limit_val = 50
        limit_text = "50ppm"
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    prompt = f"""당신은 환경부 비산배출시설 전문 진단 엔진입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[데이터 추출 및 판정 규칙]
1. 배출기준 준수: 방지시설 측정값이 {limit_val}ppm을 초과하면 "부적합", 이하이면 "적합"으로 판정하세요.
2. 데이터 필무 입력: '관리담당자', '방지시설 농도', 'LDAR 점검합계'는 문서에서 찾아 반드시 입력하세요. 
3. 마스킹 정보: 검은색 마스킹으로 안 보이는 이름이나 날짜는 "마스킹됨"으로 표기하세요. 빈칸으로 두지 마세요.
4. LDAR 요약: 개별 점검 기록을 나열하지 말고, 문서 상의 '총 점검 개소'와 '누출 건수' 합계만 찾아 1행으로 작성하세요.

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "날짜", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "날짜", "facility": "시설명", "value": "측정치", "limit": "{limit_text}", "result": "판정"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "총수", "leak_count": "누출수", "leak_rate": "0%", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "시설관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "점검이행", "expected_effect": "강화"}} ],
  "overall_opinion": "전문가 의견..."
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
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        st.error(f"분석 오류: {e}")
        return {"parsed": {}, "raw": str(e)}
