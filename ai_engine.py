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
                st.toast(f"⏳ 분석 중... ({attempt+1}/{retries})")
                time.sleep(wait)
                continue
            raise e
    raise Exception("API 호출 오류가 발생했습니다.")

def extract_pdfs_from_source(uploaded_files):
    pdf_list = []
    if not uploaded_files: return pdf_list
    if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
    for uf in uploaded_files:
        if uf.name.lower().endswith(".pdf"):
            pdf_list.append((uf.name, uf))
    return pdf_list

# ★ 해결 1: 주소(location)를 캐시 키에 포함하여 주소 변경 시 즉시 갱신되도록 복구
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
            # 가장 인식이 잘 되던 고화질(2.0배수)로 고정
            for i in range(page_count):
                page = doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 90)))
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
    # ★ 해결 2: 현재 시간 주입으로 공공데이터 시간 고정 문제 해결
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 프롬프트를 가장 잘 나오던 시절의 직관적인 구조로 복구
    prompt = f"""
당신은 한국환경공단 전문 진단 AI입니다. (시점: {current_time})
업종: {user_industry} | THC 기준: {limit_text}

[임무]
1. 문서 내 모든 연도('21, '22, '23 등)의 데이터를 전수 조사하여 추출하세요.
2. '제출인(대표자)' 이름을 manager 항목에 넣으세요.
3. 모든 방지시설 측정 수치는 'prevention' 배열에 통합하여 연도순으로 정렬하세요.
4. LDAR 기록을 'ldar' 배열에 연도별로 정리하세요.

[응답 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":100, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":97, "grade":"A"}} }},
  "manager": {{ "data": [] }},
  "prevention": {{ "data": [] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [] }},
  "risk_matrix": [],
  "improvement_roadmap": [],
  "overall_opinion": "문서 데이터를 기반으로 1500자 이상의 상세 보고서를 작성하세요. (\\n 사용)"
}}
"""
    try:
        response = generate_with_retry(model, [prompt, *measure_images])
        parsed_data = force_extract_json(response.text)
        return {"parsed": parsed_data, "raw": response.text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}
