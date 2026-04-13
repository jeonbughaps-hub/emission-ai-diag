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
import gc 

warnings.filterwarnings("ignore", category=FutureWarning)

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from utils import get_limit_ppm

def get_model(): 
    return genai.GenerativeModel("gemini-2.0-flash")

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
            doc.close()
            fbytes.seek(0)
        except Exception: continue
    if not all_texts: return None
    try:
        splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=100)
        docs = [Document(page_content=t) for t in splitter.split_text(all_texts)]
        api_key = os.environ.get("GOOGLE_API_KEY")
        emb = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
        vdb = InMemoryVectorStore.from_documents(docs, emb)
        gc.collect()
        return vdb
    except Exception: return None

def convert_and_mask_images(pdf_list):
    all_images = []
    for _, fbytes in pdf_list:
        try:
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            # ★ 핵심: 메모리 방어를 위해 이미지 크기를 최적화 (1.8배수)
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 70)))
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
    
    rag_context = ""
    if vector_db:
        try:
            docs = vector_db.similarity_search(f"{user_industry} 관리기준", k=2)
            rag_context = "\n".join([d.page_content for d in docs])
        except: pass

    # ★ 핵심 수정: 데이터 추출을 '강제'하기 위해 프롬프트 구조를 데이터/분석으로 엄격 분리
    prompt = f"""
당신은 한국환경공단 환경관리 전문가입니다. (시점: {current_time})
업종: {user_industry} | THC 기준: {limit_text}

[필수 지시사항: 데이터 복구]
이미지에서 2021, 2022, 2023년의 '제출인 이름', '방지시설 농도', 'LDAR 누출수'를 하나도 빠짐없이 추출하세요. 
데이터가 있는데 빈 칸으로 두는 것은 시스템 오류입니다. 수치가 불확실하면 가장 근접한 값을 적으세요.

[법령 대조 가이드]
참고 법령: {rag_context[:800]}

[JSON 출력 형식 - 반드시 준수]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":100, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":97, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "date": "날짜"}} ] }},
  "prevention": {{ "data": [ {{"period": "연도/반기", "facility": "시설명", "value": "농도", "result": "적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "leak_count": "0", "result": "적합"}} ] }},
  "risk_matrix": [],
  "improvement_roadmap": [],
  "overall_opinion": "법령 근거와 다개년 추이를 포함한 1500자 이상의 정밀 보고서"
}}
"""
    try:
        gc.collect()
        # JSON 모드를 강제하지 않고 일반 텍스트로 받아 후처리 (메모리 안정성)
        response = model.generate_content([prompt, *measure_images])
        raw_text = response.text
        
        # JSON 추출 후처리
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            parsed_data = json.loads(raw_text[start_idx:end_idx+1], strict=False)
        else:
            parsed_data = {}

        # 구조 보정 로직
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key in parsed_data and isinstance(parsed_data[key], list):
                parsed_data[key] = {"data": parsed_data[key]}
            elif key not in parsed_data:
                parsed_data[key] = {"data": []}
                
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}
