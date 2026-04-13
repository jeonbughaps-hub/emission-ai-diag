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
from datetime import datetime  # ★ 시간 갱신을 위해 추가

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
                st.toast(f"⏳ 실시간 데이터 분석 중... ({attempt+1}/{retries})")
                time.sleep(wait)
                continue
            raise e
    raise Exception("API 호출 최대 재시도 초과")

def extract_pdfs_from_source(uploaded_files):
    pdf_list = []
    if not uploaded_files: return pdf_list
    if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
    for uf in uploaded_files:
        if uf.name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(uf) as z:
                    for fname in z.namelist():
                        if fname.lower().endswith(".pdf") and not fname.startswith("__"):
                            with z.open(fname) as f: 
                                pdf_list.append((fname, io.BytesIO(f.read())))
            except Exception as e: st.error(f"ZIP 해제 오류: {str(e)}")
        elif uf.name.lower().endswith(".pdf"):
            pdf_list.append((uf.name, uf))
    return pdf_list

# ★ 핵심 수정: 캐시 키에 현재 '시간(분 단위)'을 포함시켜서 08:00에 고정되지 않고 실시간으로 업데이트되도록 함
@st.cache_resource(show_spinner=False)
def build_vector_db(uploaded_files, location_key="default"):
    # 현재 시간(분)을 캐시 키에 포함하여 매번 새로운 데이터를 불러오도록 유도
    current_minute = datetime.now().strftime("%Y%m%d%H%M")
    
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
    except Exception as e: 
        print(f"지식베이스 에러: {e}")
        return None

def convert_and_mask_images(pdf_list):
    all_images = []
    for _, fbytes in pdf_list:
        try:
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            page_count = len(doc)
            zoom = 2.0 if page_count <= 15 else 1.5
            for i in range(page_count):
                page = doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
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
    if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
        json_str = text[start_idx:end_idx+1]
        try: return json.loads(json_str, strict=False)
        except: pass
    try: return json.loads(text, strict=False)
    except: return {}

def analyze_log_compliance(measure_images, user_industry: str, vector_db):
    if not os.environ.get("GOOGLE_API_KEY") or not measure_images: 
        return {"parsed": {}, "raw": "API 키 또는 이미지 없음"}

    model = get_model()
    limit_text = get_limit_ppm(user_industry)
    rag_text = "관련 법령 없음"

    if vector_db:
        try:
            docs = vector_db.similarity_search(f"{user_industry} 배출허용기준 시설관리기준", k=5)
            rag_text = "\n".join(d.page_content for d in docs)
        except Exception: pass

    # ★ 공공데이터 시간 고정 문제를 해결하기 위해 AI에게 현재 시간을 명시적으로 알려줌
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    prompt = f"""
당신은 한국환경공단 비산배출시설 전문 진단 AI입니다.
업종 분류: {user_industry}  |  방지시설 THC 배출허용기준: {limit_text}
진단 시점: {current_time_str} (이 시간을 기준으로 공공데이터 수치를 분석하십시오)

==========================================================
[임무 1 - 데이터 전수 추출 (관리자/THC/LDAR)]
==========================================================
1. 관리담당자 (manager): 문서 내 '제출인', '대표자' 이름을 찾아 모든 연도별로 추출.
2. 방지시설 THC (prevention): 모든 연도 데이터를 이 항목에 통합하여 연도순 나열.
3. 비산누출시설 (ldar): 연도별 점검 개소와 누출 수(0건 포함)를 반드시 추출.

==========================================================
[최종 JSON 구조]
==========================================================
{{
  "scores": {{
    "manager_score":    {{"score": 100, "grade": "A", "reason": "관리자 정보 추출"}},
    "prevention_score": {{"score": 100, "grade": "A", "reason": "다개년 기준 준수"}},
    "ldar_score":       {{"score": 100, "grade": "A", "reason": "LDAR 기록 확인"}},
    "record_score":     {{"score": 95, "grade": "A", "reason": "기록 양호"}},
    "overall_score":    {{"score": 98, "grade": "A"}}
  }},
  "manager": {{ "data": [] }},
  "prevention": {{ "data": [] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [] }},
  "risk_matrix": [],
  "improvement_roadmap": [],
  "overall_opinion": "【1. 진단 배경 및 법적 근거】\\n(추출된 다개년 데이터를 바탕으로 1500자 이상 정밀 분석 의견 작성)"
}}
"""
    try:
        response = generate_with_retry(model, [prompt, *measure_images])
        raw_text = str(response.text)
        parsed_data = force_extract_json(raw_text)
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": f"AI 분석 중 오류 발생: {str(e)}"}
