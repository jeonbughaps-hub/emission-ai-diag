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
    # ★ 에러 철벽 방어: 무조건 JSON으로만 대답하게 고정
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
                st.toast(f"⏳ 구글 서버 대기 중... {int(wait)}초 후 재시도 ({attempt+1}/{retries})")
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
            for page in doc:
                # ★ 시력 회복: 화질을 2배수(Matrix 2, 2)로 높여 작은 글씨도 완벽히 읽게 만듦
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
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
            docs = vector_db.similarity_search(f"{user_industry} 배출허용기준 시설관리기준 LDAR 냉각탑 열교환기", k=4)
            rag_text = "\n".join(d.page_content for d in docs)
        except Exception: pass

    # ★ 앵무새 방지: 예시를 베끼지 말고 실제 데이터를 찾으라고 강력하게 명령
    prompt = f"""
당신은 한국환경공단 비산배출시설 전문 진단 AI입니다.
업종 분류: {user_industry}  |  방지시설 THC 배출허용기준: {limit_text}
[법령 지식베이스 참고 발췌]: {rag_text[:800]}

==========================================================
[임무 1 - 업로드된 문서에서 "실제 데이터"만 추출]
==========================================================
업로드된 이미지(문서)를 꼼꼼히 읽고, 표 안에 적혀있는 진짜 데이터를 추출하세요.
★경고★: 문서에 데이터가 없다면 억지로 지어내거나 예시를 베끼지 말고, 반드시 빈 배열 [ ] 을 반환하세요.

==========================================================
[임무 2 - 준수율 종합 점수 산정]
==========================================================
- manager_score, prevention_score, ldar_score, record_score를 평가하여 overall_score 산출

==========================================================
[최종 JSON 구조] 
★경고★: 아래의 배열("data": []) 내부 값들은 단지 '구조를 보여주기 위한 가짜 예시'입니다. 절대 이 예시 글자들을 그대로 출력하지 마십시오! 문서에서 찾은 '실제 글자와 숫자'로 채워 넣으십시오.
==========================================================
{{
  "scores": {{
    "manager_score":    {{"score": 100, "grade": "A", "reason": "정상 선임 완료"}},
    "prevention_score": {{"score": 100, "grade": "A", "reason": "모든 시설 기준 충족"}},
    "ldar_score":       {{"score": 100, "grade": "A", "reason": "누출 미발생"}},
    "record_score":     {{"score": 90, "grade": "A", "reason": "기록 양호"}},
    "overall_score":    {{"score": 97, "grade": "A"}}
  }},
  "manager": {{
    "data": [
      {{"period": "2023년", "name": "김환경", "date": "2023-01-01", "dept": "환경팀", "qualification": "대기환경기사"}}
    ]
  }},
  "prevention": {{
    "data": [
      {{"period": "2023년 상반기", "date": "2023-05-15", "facility": "AC-01", "value": "12.5", "limit": "{limit_text}", "accuracy_check": "양호", "result": "적합", "remark": "자가측정"}}
    ]
  }},
  "process_emission": {{
    "data": []
  }},
  "ldar": {{
    "data": [
      {{"year": "2023", "target_count": "120", "leak_count": "0", "leak_rate": "0%", "recheck_done": "해당없음", "result": "적합"}}
    ]
  }},
  "risk_matrix": [
    {{"item": "방지시설 농도 관리", "probability": "낮음", "impact": "높음", "priority": "Medium"}}
  ],
  "improvement_roadmap": [
    {{"phase": "단기(6개월 내)", "action": "활성탄 교체 주기 점검", "expected_effect": "THC 배출 농도 안정화"}}
  ],
  "overall_opinion": "【1. 진단 배경 및 법적 근거】\\n(여기에 문서 내용을 바탕으로 한 1000자 이상의 상세한 진단 텍스트를 직접 작성하시오. 절대 예시 문구를 베끼지 말 것. 줄바꿈은 반드시 \\n 사용)"
}}
"""
    try:
        response = generate_with_retry(model, [prompt, *measure_images])
        
        try:
            raw_text = str(response.text)
        except Exception as e:
            raw_text = f"{{}} (텍스트 추출 에러: {str(e)})"
            
        parsed_data = force_extract_json(raw_text)
        
        if "ldar" in parsed_data and "data" in parsed_data["ldar"]:
            for item in parsed_data["ldar"]["data"]:
                leak_val = str(item.get("leak_count", "0")).strip()
                if not leak_val.isdigit() or leak_val == "0" or leak_val == "":
                    item["leak_count"] = "0"
                    item["leak_rate"] = "0%"
                    item["result"] = "적합"
                    item["recheck_done"] = "해당없음"

        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": f"AI 분석 중 오류 발생: {str(e)}"}
