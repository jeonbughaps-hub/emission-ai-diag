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
                st.toast(f"⏳ 분석 재시도 중... ({attempt+1}/{retries})")
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

# ★ 수정: 주소(location)를 캐시 키에 추가하여 주소 변경 시 측정소가 갱신되도록 보완
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
    except Exception as e: 
        print(f"지식베이스 에러: {e}")
        return None

def convert_and_mask_images(pdf_list):
    all_images = []
    for _, fbytes in pdf_list:
        try:
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            page_count = len(doc)
            for i in range(page_count):
                page = doc[i]
                zoom = 2 if page_count <= 10 else 1.5
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
            docs = vector_db.similarity_search(f"{user_industry} 배출허용기준 시설관리기준", k=4)
            rag_text = "\n".join(d.page_content for d in docs)
        except Exception: pass

    # ★ 수정: 2)항목에 다개년 방지시설 데이터를 모두 통합하도록 프롬프트 강화
    prompt = f"""
당신은 한국환경공단 비산배출시설 전문 진단 AI입니다.
업종 분류: {user_industry}  |  방지시설 THC 배출허용기준: {limit_text}

==========================================================
[임무 1 - 다개년 방지시설 측정 데이터 통합 추출]
==========================================================
업로드된 모든 연도('21, '22, '23년 등)의 '방지시설(THC)' 측정 기록을 전수 조사하십시오.
추출된 모든 방지시설 데이터는 연도와 관계없이 무조건 "prevention" 배열에 하나로 모아주십시오. 
"process_emission"에는 순수하게 냉각탑(TOC)이나 열교환기 데이터만 넣으십시오.

==========================================================
[최종 JSON 구조 가이드] 
==========================================================
{{
  "scores": {{
    "manager_score":    {{"score": 100, "grade": "A", "reason": "관리자 정보 확인"}},
    "prevention_score": {{"score": 100, "grade": "A", "reason": "다개년 기준 준수"}},
    "ldar_score":       {{"score": 100, "grade": "A", "reason": "누출 관리 적정"}},
    "record_score":     {{"score": 90, "grade": "A", "reason": "기록 양호"}},
    "overall_score":    {{"score": 97, "grade": "A"}}
  }},
  "manager": {{ "data": [] }},
  "prevention": {{ 
    "data": [ 
       {{"period": "2021년 상반기", "date": "...", "facility": "...", "value": "...", "result": "적합"}},
       {{"period": "2022년 상반기", "date": "...", "facility": "...", "value": "...", "result": "적합"}},
       {{"period": "2023년 상반기", "date": "...", "facility": "...", "value": "...", "result": "적합"}}
    ] 
  }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [] }},
  "risk_matrix": [],
  "improvement_roadmap": [],
  "overall_opinion": "【1. 진단 배경 및 법적 근거】\\n(다개년 통합 분석 내용을 1500자 이상 상세히 기술하십시오.)"
}}
"""
    try:
        response = generate_with_retry(model, [prompt, *measure_images])
        raw_text = str(response.text)
        parsed_data = force_extract_json(raw_text)
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": f"AI 분석 중 오류 발생: {str(e)}"}
