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

warnings.filterwarnings("ignore", category=FutureWarning)

# ★ 서버에 저장된 법령 폴더 경로
KB_DIRECTORY = "knowledge_base/"

def get_model(): 
    return genai.GenerativeModel("gemini-2.0-flash")

# ★ app.py에서 호출하는 함수명을 유지하여 에러 방지
def extract_pdfs_from_source(uploaded_files):
    pdf_list = []
    if not uploaded_files: return pdf_list
    if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
    for uf in uploaded_files:
        if uf.name.lower().endswith(".pdf"):
            pdf_list.append((uf.name, uf))
    return pdf_list

# ★ app.py의 build_vector_db 호출과 호환되도록 함수명 복구 및 내부 로직 업데이트
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

    prompt = f"""
당신은 환경부 비산배출시설 전문 진단 엔진입니다. (시점: {current_time})
업종: {user_industry} | THC 기준: {limit_text}

[판정 논리]
1. 반기 분리: 표에서 상/하반기 수치가 뭉쳐있으면 반드시 2개의 행으로 분리하여 추출하세요.
2. 부적합 판정: 측정값이 {limit_text}를 단 0.01이라도 넘으면 무조건 result를 '부적합'으로 찍으세요.
3. 지식베이스 근거: 아래 법령 내용을 종합의견에 인용하세요.
{rag_context[:1000]}

[JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":100, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":97, "grade":"A"}} }},
  "manager": {{ "data": [] }},
  "prevention": {{ "data": [] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [] }},
  "risk_matrix": [],
  "improvement_roadmap": [],
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

        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key in parsed_data and isinstance(parsed_data[key], list):
                parsed_data[key] = {"data": parsed_data[key]}
            elif key not in parsed_data:
                parsed_data[key] = {"data": []}
                
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}
