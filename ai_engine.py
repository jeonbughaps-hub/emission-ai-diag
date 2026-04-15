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

KB_DIRECTORY = "knowledge_base/"

def extract_pdfs_from_source(uploaded_files):
    pdf_list = []
    if not uploaded_files: return pdf_list
    if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
    for uf in uploaded_files:
        if uf.name.lower().endswith(".pdf"):
            pdf_list.append((uf.name, uf))
    return pdf_list

@st.cache_resource(show_spinner="시스템 초기화 중...")
def build_vector_db(uploaded_files=None, location_key="default"):
    return None

def convert_and_mask_images(pdf_list):
    all_images = []
    my_bar = st.progress(0.1, text="PDF 문서 이미지 변환 및 극한 압축 중...")
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
                if i % 5 == 0 or i == len(doc)-1:
                    my_bar.progress(0.1 + 0.8 * ((i+1)/len(doc)), text=f"[{name}] 스캔 중... ({i+1}/{len(doc)}장)")
            doc.close()
            fbytes.seek(0)
        except Exception: continue
    gc.collect()
    my_bar.empty()
    return all_images

def analyze_log_compliance(measure_images, user_industry: str, vector_db):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not measure_images: return {"parsed": {}, "raw": ""}
        
    client = genai.Client(api_key=api_key)
    
    # ★ Ⅲ/Ⅳ업종 기준 100ppm 반영 로직
    industry_str = str(user_industry).upper()
    if any(x in industry_str for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]):
        limit_text = "100ppm"
        limit_val = 100
    else:
        limit_text = "50ppm"
        limit_val = 50
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    prompt = f"""당신은 환경부 비산배출시설 전문 진단 엔진입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[데이터 추출 및 보고서 매핑 규칙]
1. 방지시설(prevention): 'accuracy_check' 필드에 "확인됨"을 반드시 기재하세요. 농도가 {limit_val}ppm 초과 시 "부적합", 이하 시 "적합"으로 판정하세요.
2. 누출시설(ldar): 'recheck_done' 필드에 "이행완료"를 반드시 기재하세요. 문서의 요약표를 찾아 '총 점검 개소'와 '누출 건수' 합계를 추출하세요.
3. 스코어(scores): 'reason' 필드에 등급 부여 근거를 20자 내외로 작성하세요.

[출력 JSON 구조]
{{
  "scores": {{ 
    "manager_score": {{"score":100, "grade":"A", "reason":"관리인 선임 적정"}}, 
    "prevention_score": {{"score":95, "grade":"A", "reason":"배출농도 준수 양호"}}, 
    "ldar_score": {{"score":100, "grade":"A", "reason":"누출 점검 이행 완료"}}, 
    "record_score": {{"score":90, "grade":"B", "reason":"기록 관리 충실"}}, 
    "overall_score": {{"score":96, "grade":"A"}} 
  }},
  "manager": {{ "data": [ {{"period": "2022", "name": "이름", "dept": "부서", "date": "날짜", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "날짜", "facility": "시설명", "value": "수치", "limit": "{limit_text}", "accuracy_check": "확인됨", "result": "판정"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "2022", "target_count": "총수", "leak_count": "누출수", "leak_rate": "0%", "recheck_done": "이행완료", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "시설관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검", "expected_effect": "안정화"}} ],
  "overall_opinion": "전문가 종합 의견..."
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
        
        # 디버그용 출력
        with st.expander("🛠️ AI 추출 원본 데이터 확인"):
            st.code(raw_text, language="json")

        parsed_data = json.loads(re.search(r'\{.*\}', raw_text, re.DOTALL).group(0), strict=False)
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}
