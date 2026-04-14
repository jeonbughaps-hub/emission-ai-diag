import os
import fitz
import google.generativeai as genai
from PIL import Image
import io
import json
import streamlit as st
from datetime import datetime
import gc 
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

KB_DIRECTORY = "knowledge_base/"

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

@st.cache_resource(show_spinner="서버 법령 지식베이스 로딩 중...")
def build_vector_db(uploaded_files=None, location_key="default"):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_core.documents import Document
    from langchain_core.vectorstores import InMemoryVectorStore
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    all_texts = ""
    if os.path.exists(KB_DIRECTORY):
        for filename in os.listdir(KB_DIRECTORY):
            if filename.lower().endswith(".pdf"):
                path = os.path.join(KB_DIRECTORY, filename)
                try:
                    doc = fitz.open(path)
                    for page in doc:
                        all_texts += page.get_text() + "\n"
                    doc.close()
                except Exception: continue
    
    if uploaded_files:
        for _, fbytes in extract_pdfs_from_source(uploaded_files):
            try:
                doc = fitz.open(stream=fbytes.read(), filetype="pdf")
                for page in doc:
                    all_texts += page.get_text() + "\n"
                doc.close()
                fbytes.seek(0)
            except Exception: continue

    if not all_texts: return None

    try:
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
        docs = [Document(page_content=t) for t in splitter.split_text(all_texts)]
        api_key = os.environ.get("GOOGLE_API_KEY")
        emb = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
        return InMemoryVectorStore.from_documents(docs, emb)
    except Exception:
        return None

def convert_and_mask_images(pdf_list):
    all_images = []
    for _, fbytes in pdf_list:
        try:
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 75)))
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

    from utils import get_limit_ppm
    model = get_model()
    limit_text = get_limit_ppm(user_industry)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    rag_context = ""
    if vector_db:
        try:
            docs = vector_db.similarity_search(f"{user_industry} 시설관리기준", k=3)
            rag_context = "\n".join([d.page_content for d in docs])
        except: pass

    # ★ 데이터 누락(0점 에러) 방지를 위해 형식을 엄격히 통제하고 텍스트 길이를 최적화
    prompt = f"""
당신은 환경부 및 한국환경공단 소속의 '비산배출시설 기술진단 전문관'입니다. (시점: {current_time})
업종: {user_industry} | THC 기준: {limit_text}

[JSON 생성 절대 규칙 - 에러 방지]
1. 빈 데이터: 값이 없다면 절대 "데이터 없음" 등을 적지 말고 오직 빈 배열 `[]`만 반환하세요.
2. 부적합 판정: 측정값이 {limit_text}를 단 0.01이라도 넘으면 무조건 '부적합' 처리.
3. 텍스트 안전성: overall_opinion 등 긴 텍스트 작성 시 큰따옴표(")를 내부에 쓰지 말고, 줄바꿈은 반드시 `\\n`으로 표기하여 JSON 형태가 깨지지 않도록 하세요. (분량은 800자 내외로 핵심만 공공기관 톤으로 작성)
4. 아래 법령 내용을 분석에 인용하세요:
{rag_context[:800]}

[출력 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":100, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":97, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "선임일", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "측정일", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합/부적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "0", "leak_count": "0", "leak_rate": "0%", "result": "적합/부적합"}} ] }},
  "risk_matrix": [ {{"item": "방지시설 효율 저하", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 정밀 점검 및 교체 주기 확인", "expected_effect": "배출 농도 안정화"}} ],
  "overall_opinion": "여기에 800자 내외 정밀 보고서 작성 (줄바꿈은 \\n 사용)"
}}
"""
    try:
        gc.collect()
        response = model.generate_content([prompt, *measure_images])
        raw_text = response.text
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        parsed_data = json.loads(raw_text[start_idx:end_idx+1], strict=False) if start_idx != -1 else {}

        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key in parsed_data and isinstance(parsed_data[key], dict) and "data" in parsed_data[key]:
                if isinstance(parsed_data[key]["data"], list):
                    if any(isinstance(item, str) for item in parsed_data[key]["data"]):
                        parsed_data[key]["data"] = []
                else:
                    parsed_data[key]["data"] = []
            elif key in parsed_data and isinstance(parsed_data[key], list):
                if any(isinstance(item, str) for item in parsed_data[key]):
                    parsed_data[key] = {"data": []}
                else:
                    parsed_data[key] = {"data": parsed_data[key]}
            else:
                parsed_data[key] = {"data": []}
                
        for key in ["risk_matrix", "improvement_roadmap"]:
            if key not in parsed_data or not isinstance(parsed_data[key], list):
                parsed_data[key] = []
                
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}
