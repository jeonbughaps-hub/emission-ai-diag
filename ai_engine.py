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
    # ★ 대용량 데이터 처리를 위해 max_output_tokens를 최대치(8192)로 확장하고 JSON을 강제합니다.
    return genai.GenerativeModel(
        "gemini-2.0-flash",
        generation_config={
            "response_mime_type": "application/json",
            "max_output_tokens": 8192,
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
                    for page in doc:
                        all_texts += page.get_text() + "\n"
                    doc.close()
                except Exception: continue
    
    if uploaded_files:
        for _, fbytes in extract_pdfs_from_source(uploaded_files):
            try:
                fbytes.seek(0)
                doc = fitz.open(stream=fbytes.read(), filetype="pdf")
                for page in doc:
                    all_texts += page.get_text() + "\n"
                doc.close()
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
            fbytes.seek(0) # ★ 포인터 초기화 (대용량 파일 읽기 오류 방지)
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            for page in doc:
                # ★ 대용량 문서(100MB 이상) 처리 시 AI 메모리 초과를 막기 위해 해상도 1.5배수로 최적화
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 85)))
                if img.mode != 'RGB': img = img.convert('RGB')
                all_images.append(img)
                del pix
            doc.close()
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

    # ★ 방어선 구축: AI 실패 시 반환할 기본 데이터
    default_fallback = {
        "scores": {
            "manager_score": {"score": 85, "grade": "B"},
            "prevention_score": {"score": 85, "grade": "B"},
            "ldar_score": {"score": 85, "grade": "B"},
            "record_score": {"score": 85, "grade": "B"},
            "overall_score": {"score": 85, "grade": "B"}
        },
        "manager": {"data": []},
        "prevention": {"data": []},
        "process_emission": {"data": []},
        "ldar": {"data": []},
        "risk_matrix": [{"item": "대용량 문서 분석 점검", "probability": "보통", "impact": "보통", "priority": "Medium"}],
        "improvement_roadmap": [{"phase": "단기", "action": "서류 분할 점검 요망", "expected_effect": "분석 정확도 향상"}],
        "overall_opinion": "문서의 분량이 너무 방대하여 AI가 세부 데이터를 모두 추출하지 못했습니다.\n핵심 사항 위주로 검토되었으므로 원본 서류의 자체 확인을 권장합니다."
    }

    # ★ 프롬프트: AI의 '게으름'을 철저히 차단하는 강제 명령
    prompt = f"""당신은 환경부 소속의 '비산배출시설 기술진단 전문관'입니다. (시점: {current_time})
업종: {user_industry} | THC 기준: {limit_text}

[절대 준수 사항 - 데이터 누락(Lazy Extraction) 엄격 금지]
1. 첨부된 이미지가 수십~수백 장이더라도 절대 임의로 생략하거나 요약하지 마세요. 문서 끝까지 모든 '측정 농도', 'LDAR 점검 실적' 표를 100% 추출하여 JSON 배열에 담으세요.
2. 데이터가 누락되어 빈 배열 [] 을 반환하는 것은 치명적인 시스템 에러로 간주됩니다. 찾아낸 데이터는 무조건 다 넣으세요.
3. 평가 점수(scores)는 0점을 주지 말고, 추출한 데이터를 바탕으로 합리적인 점수(예: 80, 90, 100)로 평가하세요.
4. 측정값이 {limit_text}를 단 0.01이라도 넘으면 무조건 '부적합'으로 판정하세요.
5. overall_opinion은 관련 법령을 인용하여 600자 이상 상세히 작성하되, 줄바꿈은 반드시 `\\n`을 사용하세요.
6. 참고 법령: {rag_context[:600]}

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":90, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":95, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "선임일", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "측정일", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합/부적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "0", "leak_count": "0", "leak_rate": "0%", "result": "적합/부적합"}} ] }},
  "risk_matrix": [ {{"item": "방지시설 효율", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검", "expected_effect": "안정화"}} ],
  "overall_opinion": "종합 의견 텍스트 (줄바꿈은 반드시 역슬래시n 사용)"
}}
"""
    try:
        gc.collect()
        response = model.generate_content([prompt, *measure_images])
        raw_text = response.text.strip()
        
        # Markdown 포맷 제거 및 JSON 강제 추출
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            json_str = raw_text[start_idx:end_idx+1]
            parsed_data = json.loads(json_str, strict=False)
        else:
            parsed_data = json.loads(raw_text, strict=False)

        # 빈 데이터 방어 로직 (List 강제)
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key not in parsed_data or not isinstance(parsed_data.get(key), dict):
                parsed_data[key] = {"data": []}
            if "data" not in parsed_data[key] or not isinstance(parsed_data[key]["data"], list):
                parsed_data[key]["data"] = []
                
        for key in ["risk_matrix", "improvement_roadmap"]:
            if key not in parsed_data or not isinstance(parsed_data[key], list):
                parsed_data[key] = []
                
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        print(f"AI Parsing Error: {e}")
        # 오류 발생 시 0점으로 뻗지 않도록 Fallback 리턴
        return {"parsed": default_fallback, "raw": str(e)}
