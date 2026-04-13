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
                st.toast(f"⏳ 문서 분석 중... {int(wait)}초 후 재시도 ({attempt+1}/{retries})")
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

@st.cache_resource(show_spinner=False)
def build_vector_db(uploaded_files):
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
            zoom = 2.0 if page_count <= 20 else 1.5
            quality = 90 if page_count <= 20 else 80
            
            for i in range(page_count):
                page = doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", quality)))
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
            docs = vector_db.similarity_search(f"{user_industry} 배출허용기준 시설관리기준 LDAR 냉각탑 열교환기", k=4)
            rag_text = "\n".join(d.page_content for d in docs)
        except Exception: pass

    # ★ 핵심 수정: 다개년 데이터 전수 추출 지시 강화
    prompt = f"""
당신은 한국환경공단 비산배출시설 전문 진단 AI입니다.
업종 분류: {user_industry}  |  방지시설 THC 배출허용기준: {limit_text}

==========================================================
[임무 1 - 다개년(모든 연도) 데이터 전수 추출 및 분석]
==========================================================
문서 전체를 스캔하여 '특정 연도에 국한하지 말고' 발견되는 모든 연도('21, '22, '23년 등)의 데이터를 누락 없이 추출하십시오.
1. 관리담당자 (manager): 각 연도별 보고서의 제출인/작성자 정보를 연도별로 각각 행을 만들어 추출하십시오.
2. 대기오염방지시설 (prevention): 모든 연도의 상/하반기 측정 결과를 개별 데이터로 추출하십시오.
3. 공정배출시설 (process_emission): 냉각탑, 열교환기 등 모든 연도의 측정 내역을 추출하십시오.
4. 비산누출시설 (ldar): 연도별 점검 실적(대상 개소, 누출 개소 등)을 연도별로 정리하십시오.

==========================================================
[최종 JSON 구조] 
★중요★: "data": [] 배열 내부에 업로드된 문서에서 찾은 모든 연도의 데이터를 연도별/반기별로 각각 객체를 만들어 채우십시오.
==========================================================
{{
  "scores": {{
    "manager_score":    {{"score": 100, "grade": "A", "reason": "관리자 선임 확인"}},
    "prevention_score": {{"score": 100, "grade": "A", "reason": "배출기준 준수"}},
    "ldar_score":       {{"score": 100, "grade": "A", "reason": "누출 관리 적정"}},
    "record_score":     {{"score": 90, "grade": "A", "reason": "기록 유지 양호"}},
    "overall_score":    {{"score": 97, "grade": "A"}}
  }},
  "manager": {{ "data": [ {{"period": "2021년", "name": "...", "date": "... "}}, {{"period": "2022년", "name": "...", "date": "..."}} ] }},
  "prevention": {{ "data": [ {{"period": "2021년 상반기", "facility": "...", "value": "..."}}, {{"period": "2021년 하반기", "facility": "...", "value": "..."}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "2021", "leak_count": "0"}}, {{"year": "2022", "leak_count": "0"}} ] }},
  "risk_matrix": [],
  "improvement_roadmap": [],
  "overall_opinion": "【1. 진단 배경 및 법적 근거】\\n(추출된 다개년 데이터를 바탕으로 한 상세 분석을 1500자 이상 작성하시오. 연도별 추이가 나타나야 합니다.)"
}}
"""
    try:
        response = generate_with_retry(model, [prompt, *measure_images])
        raw_text = str(response.text)
        parsed_data = force_extract_json(raw_text)
        
        # LDAR 보정 로직
        if "ldar" in parsed_data and "data" in parsed_data["ldar"]:
            for item in parsed_data["ldar"]["data"]:
                leak_val = str(item.get("leak_count", "0")).strip()
                if not leak_val.isdigit() or leak_val == "0" or leak_val == "":
                    item["leak_count"] = "0"; item["leak_rate"] = "0%"; item["result"] = "적합"; item["recheck_done"] = "해당없음"

        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": f"AI 분석 중 오류 발생: {str(e)}"}
