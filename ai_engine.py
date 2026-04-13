import os
import fitz
import google.generativeai as genai
from PIL import Image
import io
import json
import streamlit as st
from datetime import datetime
import gc 
import warnings
import zipfile

# 구글 라이브러리 알림 숨기기
warnings.filterwarnings("ignore", category=FutureWarning)

# ★ 서버에 저장된 법령 폴더 경로
KB_DIRECTORY = "knowledge_base/"

def get_model(): 
    return genai.GenerativeModel("gemini-2.0-flash")

# ★ app.py 호출 호환 유지
def extract_pdfs_from_source(uploaded_files):
    pdf_list = []
    if not uploaded_files: return pdf_list
    if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
    for uf in uploaded_files:
        if uf.name.lower().endswith(".pdf"):
            pdf_list.append((uf.name, uf))
    return pdf_list

# ★ 서버 지식베이스 + 사용자 업로드 지식베이스 통합 로딩
@st.cache_resource(show_spinner="서버 법령 지식베이스 로딩 중...")
def build_vector_db(uploaded_files=None, location_key="default"):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_core.documents import Document
    from langchain_core.vectorstores import InMemoryVectorStore
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    all_texts = ""
    
    # 1. 서버 폴더(knowledge_base)의 PDF 먼저 읽기
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
    
    # 2. 만약 사용자가 추가로 올린 파일이 있다면 그것도 포함
    if uploaded_files:
        for _, fbytes in extract_pdfs_from_source(uploaded_files):
            try:
                doc = fitz.open(stream=fbytes.read(), filetype="pdf")
                for page in doc:
                    all_texts += page.get_text() + "\n"
                doc.close()
                fbytes.seek(0)
            except Exception: continue

    if not all_texts:
        return None

    try:
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
        docs = [Document(page_content=t) for t in splitter.split_text(all_texts)]
        api_key = os.environ.get("GOOGLE_API_KEY")
        emb = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
        return InMemoryVectorStore.from_documents(docs, emb)
    except Exception:
        return None

# ★ 이미지 변환 (메모리 최적화)
def convert_and_mask_images(pdf_list):
    all_images = []
    for _, fbytes in pdf_list:
        try:
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 75)))
                if img.mode != 'RGB': img = img.convert('RGB')
                all_images.append(img)
                del pix
            doc.close()
            fbytes.seek(0)
        except Exception: continue
    gc.collect()
    return all_images

# ★ 핵심 진단 로직 (엄격한 JSON 룰 및 2차 방어선 적용)
def analyze_log_compliance(measure_images, user_industry: str, vector_db):
    if not os.environ.get("GOOGLE_API_KEY") or not measure_images: 
        return {"parsed": {}, "raw": ""}

    from utils import get_limit_ppm
    model = get_model()
    limit_text = get_limit_ppm(user_industry)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    rag_context = ""
    if vector_db:
        try:
            docs = vector_db.similarity_search(f"{user_industry} 시설관리기준", k=3)
            rag_context = "\n".join([d.page_content for d in docs])
        except: pass

    # PDF가 깨지지 않도록 JSON 구조와 규칙을 극도로 엄격하게 통제
    prompt = f"""
당신은 환경부 비산배출시설 전문 진단 엔진입니다. (시점: {current_time})
업종: {user_industry} | THC 기준: {limit_text}

[판정 논리 및 절대 지켜야 할 규칙]
1. 빈 데이터 처리 (매우 중요): 데이터가 없다면 반드시 빈 배열 `[]`만 반환하세요. 절대 배열 안에 "데이터 없음", "추출 불가" 등의 텍스트를 넣지 마세요.
2. 반기 분리: 표에서 상/하반기 수치가 뭉쳐있으면 반드시 2개의 행으로 분리하세요.
3. 부적합 판정: 측정값이 {limit_text}를 단 0.01이라도 넘으면 무조건 result를 '부적합'으로 하세요.
4. 항목 누락 금지: 'risk_matrix'와 'improvement_roadmap'은 데이터가 부족하더라도 일반적인 환경관리 권고안을 만들어서 최소 1개 이상 반드시 채워 넣으세요.
5. 아래 법령 내용을 종합의견에 인용하세요.
{rag_context[:1000]}

[JSON 구조 - 아래 지정된 Key를 1글자도 틀리지 말고 사용할 것]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":100, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":97, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "선임일", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "측정일", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합/부적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "0", "leak_count": "0", "leak_rate": "0%", "result": "적합/부적합"}} ] }},
  "risk_matrix": [ {{"item": "방지시설 효율 저하", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 정밀 점검 및 교체 주기 확인", "expected_effect": "배출 농도 안정화"}} ],
  "overall_opinion": "법령 근거 중심의 상세 보고서 (\\n 사용)"
}}
"""
    try:
        gc.collect()
        response = model.generate_content([prompt, *measure_images])
        raw_text = response.text
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        parsed_data = json.loads(raw_text[start_idx:end_idx+1], strict=False) if start_idx != -1 else {}

        # ★ 2차 방어선: AI가 실수로 텍스트를 넣었을 경우 강제로 빈 배열로 초기화하여 표 깨짐 방지
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key in parsed_data and isinstance(parsed_data[key], dict) and "data" in parsed_data[key]:
                if isinstance(parsed_data[key]["data"], list):
                    # 만약 AI가 [{"period": "...", ...}] 대신 ["데이터 없습니다"] 처럼 문자열을 넣었을 경우 파기
                    if any(isinstance(item, str) for item in parsed_data[key]["data"]):
                        parsed_data[key]["data"] = []
                else:
                    parsed_data[key]["data"] = []
            elif key in parsed_data and isinstance(parsed_data[key], list):
                if any(isinstance(item, str) for item in parsed_data[key]):
                    parsed_data[key] = {"data": []}
                else:
                    parsed_data[key] = {"data": parsed_data[key]}
            else:
                parsed_data[key] = {"data": []}
                
        # 매트릭스와 로드맵 2차 방어선 (리스트 형태 유지)
        for key in ["risk_matrix", "improvement_roadmap"]:
            if key not in parsed_data or not isinstance(parsed_data[key], list):
                parsed_data[key] = []
                
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}
