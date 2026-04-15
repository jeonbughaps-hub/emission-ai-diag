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
# 임포트 에러 방지를 위해 최상단에 배치
try:
    import utils
except ImportError:
    utils = None

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

@st.cache_resource(show_spinner="서버 법령 지식베이스 로딩 중...")
def build_vector_db(uploaded_files=None, location_key="default"):
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_core.vectorstores import InMemoryVectorStore
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        all_texts = ""
        if os.path.exists(KB_DIRECTORY):
            for filename in os.listdir(KB_DIRECTORY):
                if filename.lower().endswith(".pdf"):
                    path = os.path.join(KB_DIRECTORY, filename)
                    try:
                        doc = fitz.open(path)
                        for page in doc:
                            all_texts += page.get_text() + "\n"
                        doc.close()
                    except Exception: continue
                    
        if not all_texts.strip(): return None
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key: return None
        
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        docs = text_splitter.create_documents([all_texts])
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
        
        vector_db = InMemoryVectorStore.from_documents(docs[:10], embeddings)
        for i in range(10, len(docs), 10):
            vector_db.add_documents(docs[i:i+10])
        return vector_db
    except Exception:
        return None

def convert_and_mask_images(pdf_list):
    all_images = []
    my_bar = st.progress(0.1, text="PDF 문서 이미지 변환 및 압축 중...")
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
        except Exception: 
            continue
    gc.collect()
    my_bar.empty()
    return all_images

def analyze_log_compliance(measure_images, user_industry: str, vector_db):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not measure_images: 
        return {"parsed": {}, "raw": ""}
        
    client = genai.Client(api_key=api_key)
    
    # 배출기준 PPM 논리 보정 (100ppm 반영)
    industry_str = str(user_industry).upper()
    if any(x in industry_str for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]):
        limit_text = "100ppm"
        limit_val = 100
    else:
        limit_text = "50ppm"
        limit_val = 50
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    rag_context = ""
    if vector_db:
        try:
            docs = vector_db.similarity_search(f"{user_industry} 시설관리기준", k=3)
            rag_context = "\n".join([d.page_content for d in docs])
        except: pass

    my_bar = st.progress(0.5, text=f"🚀 AI 분석 중... (기준: {limit_text})")

    prompt = f"""당신은 환경부 비산배출시설 전문 진단 엔진입니다. (시점: {current_time})
대상 사업장 업종: {user_industry} | THC 농도기준: {limit_text}

[데이터 판정 및 추출 규칙]
1. THC 농도 판정: 측정 농도가 {limit_val}ppm을 초과하면 "부적합", 이하이면 "적합"으로 판정하세요.
2. 데이터 필무 입력: '관리담당자', '방지시설 측정치', 'LDAR 점검합계'는 문서에서 찾아 반드시 내용을 채우세요.
3. LDAR 요약: 수천 개의 점검표를 나열하지 말고, 문서 상의 '총 점검 개소(대상)'와 '누출 건수'의 총합계만 찾아 1행으로 작성하세요.

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "날짜", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "날짜", "facility": "시설명", "value": "측정치", "limit": "{limit_text}", "result": "적합/부적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "총수", "leak_count": "누출수", "leak_rate": "0%", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "시설관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "점검이행", "expected_effect": "강화"}} ],
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
        parsed_data = {}
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            parsed_data = json.loads(match.group(0), strict=False)

        # 보고서 출력 보장을 위한 데이터 구조 강제 매핑
        dummy_row = {"period": "-", "name": "확인불가", "dept": "-", "date": "-", "qualification": "-", "facility": "-", "value": "-", "limit": limit_text, "result": "-", "year": "-", "target_count": "-", "leak_count": "-", "leak_rate": "-"}
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key not in parsed_data or not parsed_data[key].get("data"):
                parsed_data[key] = {"data": [dummy_row]}

        my_bar.empty()
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        st.error(f"분석 오류: {e}")
        return {"parsed": {}, "raw": str(e)}
