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
                st.toast(f"⏳ 데이터 정밀 분석 중... ({attempt+1}/{retries})")
                time.sleep(wait)
                continue
            raise e
    raise Exception("API 응답 지연입니다. 잠시 후 다시 시도해 주세요.")

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
            # 인식률을 위해 2.0 고화질 유지
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
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ★ 데이터 구조를 명확히 정의하여 AttributeError 방지
    prompt = f"""
당신은 한국환경공단 전문 진단 AI입니다. (현재 분석 시각: {current_time_str})
업종: {user_industry} | THC 배출기준: {limit_text}

[수행 지침]
1. 모든 페이지를 전수 조사하여 2021, 2022, 2023 등 모든 연도의 데이터를 추출하세요.
2. 각 항목(manager, prevention, ldar)은 반드시 아래 JSON 구조와 같이 "data"라는 키를 가진 딕셔너리 형태로 응답하세요.

[JSON 구조 - 이 형식을 절대 엄수하세요]
{{
  "scores": {{ 
    "manager_score": {{"score":100, "grade":"A", "reason": "관리자 선임 확인"}}, 
    "prevention_score": {{"score":100, "grade":"A", "reason": "다개년 농도 적합"}}, 
    "ldar_score": {{"score":100, "grade":"A", "reason": "누출 없음"}}, 
    "record_score": {{"score":90, "grade":"A", "reason": "기록 양호"}}, 
    "overall_score": {{"score":97, "grade":"A"}} 
  }},
  "manager": {{
    "data": [ {{"period": "연도", "name": "성명", "dept": "부서", "date": "선임일", "qualification": "자격"}} ]
  }},
  "prevention": {{
    "data": [ {{"period": "연도/반기", "date": "측정일", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합"}} ]
  }},
  "process_emission": {{ "data": [] }},
  "ldar": {{
    "data": [ {{"year": "연도", "target_count": "0", "leak_count": "0", "leak_rate": "0%", "result": "적합"}} ]
  }},
  "risk_matrix": [ {{"item": "방지시설 농도 관리", "probability": "낮음", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "점검 강화", "expected_effect": "안정화"}} ],
  "overall_opinion": "문서 데이터를 기반으로 1500자 이상의 상세 보고서를 작성하세요. (줄바꿈은 \\n 사용)"
}}
"""
    try:
        response = generate_with_retry(model, [prompt, *measure_images])
        parsed_data = force_extract_json(response.text)
        
        # 만약 AI가 실수로 딕셔너리가 아닌 리스트로 보냈을 경우를 대비한 방어 로직
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key in parsed_data and isinstance(parsed_data[key], list):
                parsed_data[key] = {"data": parsed_data[key]}
            elif key not in parsed_data:
                parsed_data[key] = {"data": []}
                
        return {"parsed": parsed_data, "raw": response.text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}
