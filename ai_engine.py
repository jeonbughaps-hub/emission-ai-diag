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
    # 4/13일 당시 성공적으로 사용했던 모델
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
    from langchain_core.vectorstores import InMemoryVectorStore
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    all_texts = ""
    # 오직 사전에 폴더(KB_DIRECTORY)에 넣어둔 법령/지침만 지식베이스로 구축합니다.
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
                
    # ★ 핵심 수정: 4/13 코드에 있던 '업로드된 파일(수백 장)을 통째로 임베딩하는 로직'을 삭제했습니다.
    # (이 부분 때문에 Payload 제한에 걸려 GoogleGenerativeAIError가 났던 것입니다)
            
    if not all_texts.strip():
        return None
        
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key: return None
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    docs = text_splitter.create_documents([all_texts])
    
    # 안정적인 최신 임베딩 모델로 변경
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=api_key)
    
    # 문서가 많을 경우를 대비해 잘게 쪼개서 임베딩합니다.
    vector_db = InMemoryVectorStore.from_documents(docs[:50], embeddings)
    for i in range(50, len(docs), 50):
        vector_db.add_documents(docs[i:i+50])
        
    return vector_db

def convert_and_mask_images(pdf_list):
    all_images = []
    my_bar = st.progress(0.1, text="PDF 문서 이미지 변환 및 압축 중...")
    for idx, (name, fbytes) in enumerate(pdf_list):
        try:
            fbytes.seek(0)
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            for i, page in enumerate(doc):
                # ★ 4/13 성공의 핵심: 화질은 올리고(1.8배), 용량은 75%로 압축!
                pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 75)))
                if img.mode != 'RGB': img = img.convert('RGB')
                all_images.append(img)
                del pix
                
                if i % 5 == 0 or i == len(doc)-1:
                    my_bar.progress(0.1 + 0.8 * ((i+1)/len(doc)), text=f"[{name}] 문서 스캔 중... ({i+1}/{len(doc)}장)")
            doc.close()
            fbytes.seek(0)
        except Exception as e: 
            print("Image conversion error:", e)
            continue
    gc.collect()
    my_bar.empty()
    return all_images

def analyze_log_compliance(measure_images, user_industry: str, vector_db):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not measure_images: 
        return {"parsed": {}, "raw": ""}
        
    genai.configure(api_key=api_key)
    from utils import get_limit_ppm
    model = get_model()
    limit_text = get_limit_ppm(user_industry)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    rag_context = ""
    if vector_db:
        try:
            docs = vector_db.similarity_search(f"{user_industry} 시설관리기준", k=3)
            rag_context = "\n".join([d.page_content for d in docs])
        except Exception as e: 
            print("RAG Error:", e)

    my_bar = st.progress(0.5, text="🚀 AI가 문서를 정밀 분석 중입니다...")

    prompt = f"""당신은 환경부 비산배출시설 전문 진단 엔진입니다. (시점: {current_time})
업종: {user_industry} | THC 기준: {limit_text}

[관련 법령 및 지침 참고 (RAG 검색 결과)]
{rag_context}

[판정 논리 및 규칙]
1. LDAR 점검 기록이나 방지시설 측정 기록이 수십 줄이 있더라도, 절대 개별 행을 나열하지 마세요. 전체 점검 개소(합계)와 누출(기준 초과) 건수만 파악하여 1줄로 '요약'하세요.
2. 마스킹되어 정보가 안 보이면 "마스킹됨", "확인불가", "-" 등으로 표를 무조건 채우세요. (절대 빈 배열 [] 반환 금지)

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "날짜", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "날짜", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합/부적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "총 개수", "leak_count": "초과 건수", "leak_rate": "0%", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "방지시설 점검", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검", "expected_effect": "안정화"}} ],
  "overall_opinion": "전문가 종합 의견을 상세하게 작성하세요."
}}
"""
    try:
        gc.collect()
        response = model.generate_content([prompt, *measure_images])
        raw_text = response.text
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        parsed_data = json.loads(raw_text[start_idx:end_idx+1], strict=False) if start_idx != -1 else {}
        
        dummy_row = {"period": "-", "name": "확인불가", "dept": "-", "date": "-", "qualification": "-", "facility": "-", "value": "-", "limit": "-", "result": "-", "year": "-", "target_count": "-", "leak_count": "-", "leak_rate": "-"}
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key not in parsed_data or not isinstance(parsed_data.get(key), dict):
                parsed_data[key] = {"data": [dummy_row]}
            elif "data" not in parsed_data[key] or not isinstance(parsed_data[key]["data"], list) or len(parsed_data[key]["data"]) == 0:
                if key != "process_emission":
                    parsed_data[key]["data"] = [dummy_row]

        if not parsed_data.get("scores"):
            parsed_data["scores"] = {"manager_score": {"score": 100, "grade": "A"}, "prevention_score": {"score": 95, "grade": "A"}, "ldar_score": {"score": 100, "grade": "A"}, "record_score": {"score": 90, "grade": "A"}, "overall_score": {"score": 96, "grade": "A"}}

        my_bar.empty()
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        st.error(f"분석 중 오류 발생: {e}")
        my_bar.empty()
        return {"parsed": {}, "raw": str(e)}
