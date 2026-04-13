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
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

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
                st.toast(f"⏳ 데이터 및 법령 통합 분석 중... ({attempt+1}/{retries})")
                time.sleep(wait)
                continue
            raise e
    raise Exception("분석 용량 초과입니다. 페이지를 줄여 시도해주세요.")

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
            # 수치 인식을 위해 2.0 고화질 고정
            zoom = 2.0
            for i in range(page_count):
                page = doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 85)))
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
    
    rag_context = ""
    if vector_db:
        try:
            docs = vector_db.similarity_search(f"{user_industry} 비산배출 시설관리기준 핵심", k=3)
            rag_context = "\n".join([d.page_content for d in docs])
        except: pass

    # ★ 핵심 수정: 데이터 추출 가이드를 매우 직관적으로 단순화
    prompt = f"""
당신은 한국환경공단 전문 진단 AI입니다. (진단시각: {current_time})
업종: {user_industry} | THC 기준: {limit_text}

[절대 우선순위 임무]
1. 이미지 내의 모든 표를 저인망식으로 스캔하여 '2021~2023' 모든 연도의 실측 데이터를 추출하세요.
2. '제출인' 또는 '대표자' 이름을 'manager' 데이터에 반드시 넣으세요.
3. 데이터가 존재함에도 빈 칸[]으로 응답하는 것은 심각한 오류입니다. 무조건 수치를 찾아 채우세요.

[법규 지침 참고]
{rag_context[:800]}

[JSON 형식 엄수]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":100, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":97, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "date": "날짜"}} ] }},
  "prevention": {{ "data": [ {{"period": "연도/반기", "facility": "시설명", "value": "농도", "result": "적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "leak_count": "0", "result": "적합"}} ] }},
  "risk_matrix": [],
  "improvement_roadmap": [],
  "overall_opinion": "법령과 실측 데이터를 연계한 1500자 이상의 정밀 분석 (\\n 사용)"
}}
"""
    try:
        response = generate_with_retry(model, [prompt, *measure_images])
        parsed_data = force_extract_json(response.text)
        
        # 데이터 구조 보정 (리스트 방지)
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key in parsed_data and isinstance(parsed_data[key], list):
                parsed_data[key] = {"data": parsed_data[key]}
            elif key not in parsed_data:
                parsed_data[key] = {"data": []}
                
        return {"parsed": parsed_data, "raw": response.text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}
