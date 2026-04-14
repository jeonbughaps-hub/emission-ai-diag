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
    # ★ 예전에 잘 작동했던 직관적인 설정으로 복귀하되, 
    # 모델만 현존 최강의 비전 성능을 가진 'Gemini 2.0 Pro'로 업그레이드합니다.
    return genai.GenerativeModel(
        "gemini-2.0-pro-exp",
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    )

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
                    for page in doc: all_texts += page.get_text() + "\n"
                    doc.close()
                except Exception: continue
    
    if uploaded_files:
        for _, fbytes in extract_pdfs_from_source(uploaded_files):
            try:
                fbytes.seek(0)
                doc = fitz.open(stream=fbytes.read(), filetype="pdf")
                for page in doc: all_texts += page.get_text() + "\n"
                doc.close()
            except Exception: continue

    if not all_texts: return None

    try:
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
        docs = [Document(page_content=t) for t in splitter.split_text(all_texts)]
        api_key = os.environ.get("GOOGLE_API_KEY")
        emb = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
        return InMemoryVectorStore.from_documents(docs, emb)
    except Exception: return None

def convert_and_mask_images(pdf_list):
    # ★ 예전에 가장 안정적으로 굴러가던 "순수 이미지 변환" 방식으로 완전 복귀!
    all_images = []
    if not pdf_list: return []
    
    for _, fbytes in pdf_list:
        try:
            fbytes.seek(0)
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            for page in doc:
                # 화질을 안정적인 1.5배수로 설정
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 85)))
                if img.mode != 'RGB': img = img.convert('RGB')
                all_images.append(img)
                del pix
            doc.close()
        except Exception as e:
            print("Convert Error:", e)
            continue
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
            docs = vector_db.similarity_search(f"{user_industry} 시설관리기준", k=2)
            rag_context = "\n".join([d.page_content for d in docs])
        except: pass

    # ★ 군더더기 없는 깔끔한 오리지널 프롬프트
    prompt = f"""당신은 환경부 소속 '비산배출시설 기술진단 전문관'입니다. (시점: {current_time})
첨부된 운영기록부 이미지들을 꼼꼼히 스캔하여 아래 항목의 데이터를 JSON으로 완벽히 추출 및 평가하세요.
업종 기준: {limit_text}

[임무]
1. manager: 관리담당자 선임 기록 (연도, 이름, 부서, 선임일 등) 추출
2. prevention: 방지시설 측정 기록 추출 (농도가 {limit_text} 초과 시 result를 "부적합"으로 기재)
3. process_emission: 공정배출시설 측정 기록 추출
4. ldar: 비산누출시설(LDAR) 점검 실적 추출
5. scores: 추출된 데이터를 바탕으로 점수(0~100) 산정 (문제가 없으면 90점 이상 부여)
6. overall_opinion: 500자 이상 전문적인 총평 작성 (줄바꿈 `\\n` 필수)

* 데이터가 없는 항목은 임의로 지어내지 말고, 반드시 빈 배열 [] 을 반환하세요.

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":90, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":95, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "선임일", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "측정일", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합/부적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "0", "leak_count": "0", "leak_rate": "0%", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "방지시설 효율", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검", "expected_effect": "안정화"}} ],
  "overall_opinion": "종합 의견 상세 작성 (줄바꿈 \\n 사용)"
}}
"""
    try:
        # ★ 예전처럼 이미지를 한 번에 묶어서 모델로 쾌속 전송합니다!
        response = model.generate_content([prompt, *measure_images], request_options={"timeout": 120})
        parsed_data = json.loads(response.text.strip(), strict=False)
        
        # 빈 데이터 구조 안정성 확보
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key not in parsed_data or not isinstance(parsed_data.get(key), dict):
                parsed_data[key] = {"data": []}
            if "data" not in parsed_data[key] or not isinstance(parsed_data[key]["data"], list):
                parsed_data[key]["data"] = []
                
        return {"parsed": parsed_data, "raw": response.text}
        
    except Exception as e:
        print("Analysis Error:", e)
        # 에러 발생 시 UI가 박살나지 않도록 기본 골격 반환
        fallback_data = {
            "scores": {
                "manager_score": {"score": 0, "grade": "F"}, "prevention_score": {"score": 0, "grade": "F"},
                "ldar_score": {"score": 0, "grade": "F"}, "record_score": {"score": 0, "grade": "F"},
                "overall_score": {"score": 0, "grade": "F"}
            },
            "manager": {"data": []}, "prevention": {"data": []}, "process_emission": {"data": []}, "ldar": {"data": []},
            "risk_matrix": [], "improvement_roadmap": [],
            "overall_opinion": f"서버 통신 중 데이터 분석 오류가 발생했습니다: {str(e)}"
        }
        return {"parsed": fallback_data, "raw": str(e)}
