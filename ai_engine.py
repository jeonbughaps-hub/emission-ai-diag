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

warnings.filterwarnings("ignore", category=FutureWarning)

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from utils import get_limit_ppm

# ★ 서버에 저장된 법령 폴더 경로
KB_DIRECTORY = "knowledge_base/"

def get_model(): 
    return genai.GenerativeModel("gemini-2.0-flash")

# ★ 서버 폴더에서 법령을 자동으로 읽어오는 새로운 함수
@st.cache_resource(show_spinner="법령 지식베이스 로딩 중...")
def build_fixed_vector_db():
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
                except Exception as e:
                    print(f"파일 로드 에러({filename}): {e}")
    
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

    model = get_model()
    limit_text = get_limit_ppm(user_industry)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 지식베이스 검색 (서버에 상주된 데이터 우선 활용)
    rag_context = ""
    if vector_db:
        try:
            docs = vector_db.similarity_search(f"{user_industry} 시설관리기준", k=3)
            rag_context = "\n".join([d.page_content for d in docs])
        except: pass

    # ★ 판정 논리 강제 프롬프트
    prompt = f"""
당신은 환경부 비산배출시설 전문 진단 엔진입니다. (시점: {current_time})
업종: {user_industry} | THC 기준: {limit_text}

[필수 추출 및 판정 논리]
1. 반기 분리: 표에서 '43.69 / 65.2'처럼 값이 2개면 반드시 상/하반기 행을 나누어 추출하세요.
2. 수치 판정: 측정값이 {limit_text}를 단 0.01이라도 넘으면 result를 '부적합'으로 찍으세요.
3. 지식베이스 근거: 아래 제공된 법령 텍스트를 분석 보고서에 적극 인용하세요.
{rag_context[:1000]}

[JSON 출력]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":100, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":97, "grade":"A"}} }},
  "manager": {{ "data": [] }},
  "prevention": {{ "data": [] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [] }},
  "risk_matrix": [],
  "improvement_roadmap": [],
  "overall_opinion": "법령 근거를 포함한 1500자 이상의 정밀 분석 보고서 (\\n 사용)"
}}
"""
    try:
        gc.collect()
        response = model.generate_content([prompt, *measure_images])
        raw_text = response.text
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        parsed_data = json.loads(raw_text[start_idx:end_idx+1], strict=False) if start_idx != -1 else {}

        # 구조 보정
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key in parsed_data and isinstance(parsed_data[key], list):
                parsed_data[key] = {"data": parsed_data[key]}
            elif key not in parsed_data:
                parsed_data[key] = {"data": []}
                
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}
