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
    # ★ 구글 AI에게 순수 JSON으로만 대답하도록 강제 설정
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
                st.toast(f"⏳ 구글 서버 혼잡... {int(wait)}초 후 재시도 ({attempt+1}/{retries})")
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
                pix = page.get_pixmap(matrix=fitz.Matrix(1, 1))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg")))
                if img.mode != 'RGB': img = img.convert('RGB')
                all_images.append(img)
            fbytes.seek(0)
        except Exception: continue
    return all_images

# ★ 렌더링 오류를 일으키던 코드를 제거하고, 가장 안전한 방식으로 변경했습니다.
def force_extract_json(text) -> dict:
    if not text: return {}
    text = str(text).strip()
    
    # '{' 와 '}' 기호 사이의 텍스트만 안전하게 추출합니다.
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
        json_str = text[start_idx:end_idx+1]
        try:
            return json.loads(json_str, strict=False)
        except:
            pass
            
    try: 
        return json.loads(text, strict=False)
    except: 
        return {}

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

    prompt = f"""
당신은 환경부 비산배출시설 전문 진단 AI입니다.
업종 분류: {user_industry}  |  방지시설 THC 배출허용기준: {limit_text}
[법령 지식베이스 참고 발췌]: {rag_text[:800]}

==========================================================
[임무 1 - 업로드된 모든 연도 데이터 전수 추출 및 오류 방지]
==========================================================
제공된 모든 문서 이미지를 끝까지 스캔하여, 2022년, 2023년, 2024년 등 문서에 존재하는 '모든 연도'의 측정 데이터를 누락 없이 전부 JSON 배열에 누적하여 추출하십시오.
1. 중복 추출 절대 금지.
2. 시각적 오인식 방지: 표의 테두리 선을 숫자 '1'로 착각하지 마십시오 (예: 10.19를 110.19로 오인식 절대 금지).
3. 관리담당자: 선임되어 있으면 무조건 적합(A).
4. 대기오염방지시설(THC): 'prevention' 배열에 추출. (일반적인 분류명 대신 AC-01 같은 구체적인 시설명칭을 기재할 것. 농도가 {limit_text} 이하이면 '적합')
5. 공정배출시설(냉각탑, 열교환기 등): 'process_emission' 배열에 별도로 추출.
   - 냉각탑(TOC): 50ppm 이하 '적합'
   - 열교환기: 개별 농도를 적지 말고, 전단과 후단의 '농도 편차'만을 계산하여 1ppm 이내이면 '적합'
6. 비산누출시설(LDAR): 누출 초과 건수가 '0'이거나, 30일 이내에 조치완료되었거나, '미실시'인 경우 무조건 누출건수를 '0'으로 처리하고 판정을 '적합'으로 하십시오.

==========================================================
[임무 2 - 준수율 종합 점수 산정]
==========================================================
- manager_score   : 선임 시 무조건 100점
- prevention_score: 기준 만족 시 100점
- ldar_score      : 누출 초과 0건이거나 조치 완료, 미실시 시 무조건 100점
- record_score    : 기록 충실성 (기본 90~100점)
- overall_score   : 위 4개 평균 점수

==========================================================
[임무 3 - 전문 보고서 텍스트 생성]  ★ 1,500자 이상 ★
==========================================================
overall_opinion 필드에 아래 5개 목차 구조를 지켜 작성.
【1. 진단 배경 및 법적 근거】
【2. 연도별 운영기록 합법성 평가】
【3. 현장 시설 관리 상태 진단】
【4. 위험도 및 행정처분 가능성 평가】
【5. 중장기 개선 로드맵 및 정책 제언】

==========================================================
[최종 JSON 구조] (반드시 이 구조와 키 값을 지켜서 순수한 JSON 형식으로만 답변할 것)
==========================================================
{{
  "scores": {{
    "manager_score":    {{"score": 100, "grade": "A", "reason": "정상 선임 완료"}},
    "prevention_score": {{"score": 100, "grade": "A", "reason": "모든 시설 기준 충족"}},
    "ldar_score":       {{"score": 100, "grade": "A", "reason": "누출 미발생 또는 조치 완료"}},
    "record_score":     {{"score": 90, "grade": "A", "reason": "기록 양호"}},
    "overall_score":    {{"score": 97, "grade": "A"}}
  }},
  "manager": {{ "data": [] }},
  "prevention": {{ "data": [] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [] }},
  "risk_matrix": [],
  "improvement_roadmap": [],
  "overall_opinion": "여기에 작성 (★절대 실제 엔터키를 치지 마십시오. 반드시 \\n 기호를 사용하여 줄바꿈 할 것)"
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

        if "scores" in parsed_data and "ldar_score" in parsed_data["scores"]:
            all_zero = all(str(item.get("leak_count", "0")) == "0" for item in parsed_data.get("ldar", {}).get("data", []))
            if all_zero:
                parsed_data["scores"]["ldar_score"]["score"] = 100
                parsed_data["scores"]["ldar_score"]["grade"] = "A"
                parsed_data["scores"]["ldar_score"]["reason"] = "누출 미발생 또는 조치 완료"
                
                scores = parsed_data["scores"]
                try:
                    s1 = int(scores.get("manager_score", {}).get("score", 0))
                    s2 = int(scores.get("prevention_score", {}).get("score", 0))
                    s3 = int(scores.get("ldar_score", {}).get("score", 0))
                    s4 = int(scores.get("record_score", {}).get("score", 0))
                    avg = int((s1 + s2 + s3 + s4) / 4)
                    
                    if avg >= 90: grade = "A"
                    elif avg >= 80: grade = "B"
                    elif avg >= 70: grade = "C"
                    elif avg >= 60: grade = "D"
                    else: grade = "F"
                    
                    parsed_data["scores"]["overall_score"]["score"] = avg
                    parsed_data["scores"]["overall_score"]["grade"] = grade
                except Exception: pass

        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": f"AI 분석 중 오류 발생: {str(e)}"}
