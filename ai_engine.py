import os
import fitz
from google import genai
from google.genai import types
from PIL import Image
import io
import json
import re
import streamlit as st
from datetime import datetime
import gc 
import warnings
import zipfile 
import time

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS

warnings.filterwarnings("ignore", category=FutureWarning)

FAISS_DB_DIR = "faiss_vector_db"

def get_api_key():
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        try:
            key = st.secrets.get("GOOGLE_API_KEY")
        except:
            return None
    return key

def build_vector_db(uploaded_kb_file):
    if not uploaded_kb_file: return False
    
    api_key = get_api_key()
    if not api_key:
        st.error("API 키를 찾을 수 없습니다.")
        return False

    kb_text = ""
    try:
        with zipfile.ZipFile(io.BytesIO(uploaded_kb_file.read())) as z:
            for inner_file in z.namelist():
                if "__MACOSX" in inner_file or inner_file.split("/")[-1].startswith("."): continue
                if inner_file.lower().endswith(".pdf"):
                    pdf_bytes = z.read(inner_file)
                    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    for page in doc:
                        kb_text += page.get_text("text") + "\n"
                    doc.close()
    except Exception as e:
        st.error(f"지식베이스 추출 실패: {e}")
        return False

    if not kb_text.strip(): return False

    try:
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_text(kb_text)
        embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=api_key)
        vector_db = FAISS.from_texts(chunks, embeddings)
        vector_db.save_local(FAISS_DB_DIR)
        return True
    except Exception as e:
        st.error(f"벡터 DB 생성/저장 실패: {e}")
        return False

def load_vector_db():
    api_key = get_api_key()
    if not api_key: return None
            
    if os.path.exists(FAISS_DB_DIR):
        try:
            embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=api_key)
            vector_db = FAISS.load_local(FAISS_DB_DIR, embeddings, allow_dangerous_deserialization=True)
            return vector_db
        except:
            return None
    return None

def extract_pdfs_from_source(uploaded_files):
    pdf_list = []
    if not uploaded_files: return pdf_list
    if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
    
    for uf in uploaded_files:
        file_name = uf.name.lower()
        if file_name.endswith(".pdf"):
            pdf_list.append((uf.name, uf))
        elif file_name.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(uf.read())) as z:
                    for inner_file in z.namelist():
                        if "__MACOSX" in inner_file or inner_file.split("/")[-1].startswith("."): continue
                        if inner_file.lower().endswith(".pdf"):
                            pdf_bytes = z.read(inner_file)
                            pdf_list.append((inner_file, io.BytesIO(pdf_bytes)))
            except Exception as e:
                st.error(f"ZIP 압축 해제 중 오류: {e}")
    return pdf_list

def convert_and_mask_images(pdf_list):
    all_images = []
    my_bar = st.progress(0.1, text="PDF 문서 정밀 스캔 중...")
    for idx, (name, fbytes) in enumerate(pdf_list):
        try:
            fbytes.seek(0)
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 80)))
                if img.mode != 'RGB': img = img.convert('RGB')
                all_images.append(img)
                del pix
                gc.collect() 
            doc.close()
        except Exception: continue
    my_bar.empty()
    return all_images

def analyze_log_compliance(measure_images, user_industry: str, vector_db):
    api_key = get_api_key()
    if not api_key: 
        st.error("API 키를 찾을 수 없습니다. Secrets 설정을 확인하세요.")
        return {"parsed": {}, "raw": "API 키 오류"}
            
    client = genai.Client(api_key=api_key)
    
    industry_str = str(user_industry).upper()
    if any(x in industry_str for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]):
        limit_text = "100ppm 미만 또는 저감효율 80% 이상"
        ppm_limit = "100"
        eff_limit = "80"
    else:
        limit_text = "50ppm 미만 또는 저감효율 90% 이상"
        ppm_limit = "50"
        eff_limit = "90"
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    retrieved_knowledge = ""
    if vector_db is not None:
        try:
            search_query = f"비산배출시설 {user_industry} 방지시설 냉각탑 열교환기 관리기준 및 행정처분"
            docs = vector_db.similarity_search(search_query, k=4)
            retrieved_knowledge = "\n".join([doc.page_content for doc in docs])
        except:
            retrieved_knowledge = ""

    prompt = f"""당신은 환경부 비산배출시설 기술진단 전문 AI입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[★ 최우선 지시사항 : 데이터 100% 전수조사 추출 ★]
1. 첨부된 모든 문서/이미지를 스캔하여 아래 데이터를 찾아 배열에 담으세요.
2. 방지시설 농도 (prevention): 문서에 기록된 '실제 측정일자', '시설명', '측정결과(전단/후단)' 값을 추출하세요. (THC 측정기기 정도검사 결과는 절대 제외)
   - 🚨 날짜(date) 추출 경고: 문서에 적힌 해당 데이터의 '실제 측정 연도와 월'을 절대 혼동하지 마세요. (예: 24년 1월 측정값을 24년 10월로 잘못 추출하는 환각 엄격히 금지)
   - 🚨 결과(value) 작성 규칙 (반드시 아래 양식 준수):
     > 전단과 후단이 모두 측정된 경우: "전단: OOppm, 후단: OOppm (효율 OO%)"
     > 후단만 측정된 경우: "후단: OOppm" (※ 후단만 있는 경우 효율을 임의로 계산하거나 적지 마세요)
   - 🚨 저감효율 예외 판정: 측정값이 {ppm_limit}ppm을 초과하더라도, 문서상 '저감효율'이 {eff_limit}% 이상인 경우 최종 판정(result)은 반드시 '적합'으로 처리하세요.
3. LDAR 누출 점검 (ldar): 2022년, 2023년, 2024년, 2025년 등 문서에 존재하는 '모든 연도'의 점검 실적을 단 한 해도 빼놓지 말고 전수조사하여 각각 추출하세요.

[🚨 냉각탑 및 열교환기 정밀 분석 필수 - 환각 엄격 금지 🚨]
- ❗️문서에 냉각탑이나 열교환기 관련 점검 기록이 **실제로 존재하는 경우에만** 추출하여 `cooling` 배열에 담으세요.
- ❗️만약 관련 기록이 전혀 없다면, 절대 지어내지 말고 `cooling` 배열을 빈 배열(`[]`)로 비워두세요.
- 기록이 존재할 경우, 측정 날짜(date)를 반드시 추출하여 `date` 속성에 기입하세요. (예: "2024-05-12")

[🚫 강력한 환각(Hallucination) 방지 지시사항 🚫]
서술형 의견(overall_opinion 등)을 작성할 때, 문서에서 실제로 추출된 연도, 시설명, 수치만을 100% 팩트 기반으로 서술하세요. 문서에 없는 과거 이력을 상상하거나 지어내지 마십시오. 문자열 안에 큰따옴표(")를 사용할 때는 반드시 백슬래시(\)로 이스케이프 처리하세요.

[★ 지식베이스 ★]
{retrieved_knowledge if retrieved_knowledge else "기본 환경 지식 활용"}

[★ 출력 형식 ★]
반드시 마크다운 없이 순수 JSON 객체로만 출력하세요. 속성명과 구조를 절대 바꾸지 마세요.
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"B"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "2024-01-11", "facility": "흡착에의한시설(7)", "value": "전단: 350ppm, 후단: 30.5ppm (효율 91.2%)", "limit": "{limit_text}", "result": "적합"}} ] }},
  "ldar": {{ "data": [ {{"year": "2025", "target_count": "10", "leak_count": "0", "leak_rate": "0%", "recheck_done": "이행완료", "result": "적합"}} ] }},
  "cooling": {{ "data": [
    {{"date": "2023-04-10", "facility": "냉각탑", "value": "2.6ppm", "limit": "50ppm 미만", "result": "적합"}}
  ]}},
  "risk_matrix": [ {{"item": "시설관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검 강화", "expected_effect": "효율 안정화"}} ],
  "priority_actions": [ {{"priority": "1", "action": "냉각탑 TOC 정기검사", "deadline": "1개월 이내", "owner": "환경안전팀"}} ],
  "law_references": [ {{"law_name": "비산배출시설 관리기준", "article": "관련 조문", "summary": "냉각수 TOC 50ppm 미만 유지 의무", "checked_date": "2026-10-18"}} ],
  "followup_actions": [ {{"action": "열교환기 편차 점검", "owner": "관리자", "deadline": "분기 내", "status": "대기"}} ],
  "overall_opinion": "반드시 추출된 실제 데이터만을 기반으로 작성. 절대 가상의 과거 이력을 지어내지 말 것."
}}
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt] + measure_images,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        
        raw_text = response.text.strip()
        
        try:
            parsed_data = json.loads(raw_text, strict=False)
        except json.JSONDecodeError:
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            parsed_data = json.loads(raw_text, strict=False)
                
        return {"parsed": parsed_data, "raw": raw_text}
    
    except Exception as e:
        st.error(f"1단계 데이터 추출 중 API 오류 발생: {e}")
        return {"parsed": {}, "raw": f"에러 발생: {e}"}

def generate_advanced_air_advice(station_name: str, pm10_val: str, o3_val: str):
    time.sleep(3) 
    api_key = get_api_key()
    if not api_key: return "대기질 API 키 설정 오류."
            
    client = genai.Client(api_key=api_key)
    prompt = f"""
당신은 국립환경과학원 수준의 대기환경 전문 연구원입니다.
관할 측정소({station_name})의 현재 실시간 대기질은 미세먼지(PM10): {pm10_val} ㎍/m³, 오존(O3): {o3_val} ppm 입니다.
이 사업장은 '유기용제(VOCs)'를 다량 취급하는 비산배출시설입니다.

아래 3가지 소제목을 사용하여 총 800자 분량의 전문적인 '환경 관리 지침'을 작성하세요.
【1. 지역 대기질 현황 및 광화학적 영향 분석】
【2. 현장 비산배출원 선제적 통제 가이드】
【3. 방지시설 및 LDAR 연계 집중 관리 방안】
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0.4)
        )
        return response.text.strip()
    except Exception as e:
        st.error(f"2단계 전문가 제언 중 API 오류 발생: {e}")
        return "AI 모델 통신 오류로 전문가 제언 생성을 일시 생략합니다."
