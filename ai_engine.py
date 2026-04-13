import os
import fitz
import google.generativeai as genai
from PIL import Image
import io
import json
import re
import time
import random
import zipfile
import streamlit as st
from datetime import datetime

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from utils import get_limit_ppm

def get_model(): 
    return genai.GenerativeModel(
        "gemini-2.0-flash",
        generation_config={"response_mime_type": "application/json"}
    )

def generate_with_retry(model, content_list, retries=5, delay=3):
    for attempt in range(retries):
        try: return model.generate_content(content_list)
        except Exception as e:
            if "429" in str(e) or "Resource exhausted" in str(e) or "503" in str(e):
                wait = delay * (1.5 ** attempt) + random.uniform(0, 1)
                st.toast(f"⏳ 서버 부하 조절 중... ({attempt+1}/{retries})")
                time.sleep(wait)
                continue
            raise e
    raise Exception("서버 메모리 또는 API 한도 초과입니다. 잠시 후 시도해주세요.")

def extract_pdfs_from_source(uploaded_files):
    pdf_list = []
    if not uploaded_files: return pdf_list
    if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
    for uf in uploaded_files:
        if uf.name.lower().endswith(".pdf"):
            pdf_list.append((uf.name, uf))
    return pdf_list

@st.cache_resource(show_spinner=False)
def build_vector_db(uploaded_files, location_key="default"):
    # 지식베이스 서버 고정 로직의 기초가 되는 부분입니다.
    if not uploaded_files: return None
    all_texts = ""
    for _, fbytes in extract_pdfs_from_source(uploaded_files):
        try:
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            for page in doc: all_texts += page.get_text() + "\n"
            fbytes.seek(0)
        except Exception: continue
    if not all_texts: return None
    try:
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        docs = [Document(page_content=t) for t in splitter.split_text(all_texts)]
        api_key = os.environ.get("GOOGLE_API_KEY")
        emb = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
        return InMemoryVectorStore.from_documents(docs, emb)
    except Exception: return None

def convert_and_mask_images(pdf_list):
    all_images = []
    for _, fbytes in pdf_list:
        try:
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            page_count = len(doc)
            # ★ 메모리 최적화: 전체 페이지가 많으면 1.2배수, 적으면 2.0배수로 유연하게 대처
            zoom_val = 2.0 if page_count <= 10 else 1.2
            for i in range(page_count):
                page = doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom_val, zoom_val))
                # JPEG 압축률을 75로 조정하여 전송 용량 최적화
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 75)))
                if img.mode != 'RGB': img = img.convert('RGB')
                all_images.append(img)
            fbytes.seek(0)
        except Exception: continue
    return all_images

def force_extract_json(text) -> dict:
    if not text: return {}
    text = str(text).strip()
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    if start_idx != -1 and end_idx != -1:
        json_str = text[start_idx:end_idx+1]
        try: return json.loads(json_str, strict=False)
        except: pass
    return {}

def analyze_log_compliance(measure_images, user_industry: str, vector_db):
    if not os.environ.get("GOOGLE_API_KEY") or not measure_images: 
        return {"parsed": {}, "raw": ""}

    model = get_model()
    limit_text = get_limit_ppm(user_industry)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 지식베이스(RAG) 검색 강화: 실제 법령 지문을 분석 프롬프트에 주입
    rag_context = ""
    if vector_db:
        try:
            docs = vector_db.similarity_search(f"{user_industry} 비산배출 시설관리기준", k=3)
            rag_context = "\n".join([d.page_content for d in docs])
        except: pass

    prompt = f"""
당신은 한국환경공단 전문 진단 AI입니다. (현재 시각: {current_time})
업종: {user_industry} | THC 기준: {limit_text}
[참고 법규/지침]: {rag_context[:1000]}

[필수 임무]
1. 모든 연도 데이터를 전수 추출하고 "prevention"에 통합하세요.
2. 지식베이스의 법적 기준과 사업장의 측정값을 비교하여 "overall_opinion"에 1500자 이상의 정밀 분석 보고서를 작성하세요.
3. 데이터가 리스트 형태로 반환되지 않도록 구조를 엄격히 준수하세요.

[JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":100, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":97, "grade":"A"}} }},
  "manager": {{ "data": [] }},
  "prevention": {{ "data": [] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [] }},
  "risk_matrix": [],
  "improvement_roadmap": [],
  "overall_opinion": "법령 근거를 포함한 상세 보고서 (\\n 사용)"
}}
"""
    try:
        response = generate_with_retry(model, [prompt, *measure_images])
        parsed_data = force_extract_json(response.text)
        
        # 구조 보정 (pdf_generator 에러 방지)
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key in parsed_data and isinstance(parsed_data[key], list):
                parsed_data[key] = {"data": parsed_data[key]}
            elif key not in parsed_data:
                parsed_data[key] = {"data": []}
                
        return {"parsed": parsed_data, "raw": response.text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}
