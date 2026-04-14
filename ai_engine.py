import os
import fitz
import google.generativeai as genai
from PIL import Image
import io
import json
import re
import streamlit as st
from datetime import datetime

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

KB_DIRECTORY = "knowledge_base/"

def get_model(): 
    # 과거에 가장 안정적이었던 2.0-flash 모델로 복귀 (출력 토큰 최대치 확보)
    return genai.GenerativeModel(
        "gemini-2.0-flash",
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.1,
            "max_output_tokens": 8192
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
    """
    ★ 과거의 안정적인 이미지 변환 방식으로 복귀 
    (단, Payload 초과 방지를 위해 해상도와 품질을 최적화)
    """
    all_images = []
    if not pdf_list: return []
    
    my_bar = st.progress(0, text="PDF 문서를 AI 전송용 이미지로 변환 중입니다...")
    
    for idx, (name, fbytes) in enumerate(pdf_list):
        try:
            fbytes.seek(0)
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            total_pages = len(doc)
            
            for i in range(total_pages):
                page = doc.load_page(i)
                # 황금 비율: 너무 무겁지 않으면서 글씨는 선명하게 보이는 1.2x 매트릭스
                pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 75)))
                if img.mode != 'RGB': img = img.convert('RGB')
                all_images.append(img)
                
                if i % 5 == 0:
                    my_bar.progress((i / total_pages), text=f"문서 변환 중... ({i}/{total_pages}장)")
            doc.close()
        except Exception as e:
            print("Convert Error:", e)
            continue
            
    my_bar.empty()
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

    my_bar = st.progress(0.5, text="AI가 문서 전체를 스캔하여 데이터를 추출 중입니다. (약 1분 소요)")

    # ★ 답변 짤림 방지를 위한 초강력 요약 명령 프롬프트
    prompt = f"""당신은 환경부 소속 '비산배출시설 기술진단 전문관'입니다.
첨부된 문서 이미지 전체를 정독하여 아래 4가지 데이터를 추출하세요.
업종 기준: {limit_text}

[매우 중요한 절대 규칙]
LDAR(비산누출시설) 점검 기록이나 방지시설 측정 기록이 수십 페이지에 걸쳐 수백 줄이 있더라도, **절대 개별 행(Row)을 모두 나열하지 마세요.** 답변이 길어져 시스템이 다운됩니다.
반드시 문서 전체를 읽고 **전체 개소(합산), 누출/부적합 건수만 1~2개의 JSON 객체로 '요약'해서 출력**하세요.

[임무]
1. manager: 관리담당자 선임 기록 (연도, 이름 등) 추출
2. prevention: 방지시설 운영/측정 기록을 연도별/반기별로 요약하여 추출
3. ldar: "비산누출시설 측정결과" 표에서 전체 점검 개수와 기준 초과 개수만 1줄로 요약 추출
4. scores: 문서에 데이터가 존재하면 각 항목 90점 이상 부여
5. overall_opinion: 500자 이상 전문적인 총평 작성 (줄바꿈 `\\n` 필수)

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "날짜", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "날짜", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합/부적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "요약된 총 개수", "leak_count": "초과 건수", "leak_rate": "0%", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "방지시설 점검", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검", "expected_effect": "안정화"}} ],
  "overall_opinion": "여기에 종합 의견 상세 작성 (줄바꿈 \\n 사용)"
}}
"""
    try:
        # 안전 필터 해제 및 타임아웃 넉넉히 설정하여 한 번에 전송!
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
        
        response = model.generate_content(
            [prompt, *measure_images], 
            safety_settings=safety_settings,
            request_options={"timeout": 300}
        )
        
        raw_text = response.text.strip()
        
        # ★ JSON 구조대 (Regex Salvage): 혹시라도 답변이 끊겼을 때 정상적인 JSON 부분만 낚아챔
        parsed_data = {}
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            json_str = match.group(0)
            try:
                parsed_data = json.loads(json_str, strict=False)
            except json.JSONDecodeError:
                # 마지막이 끊겼을 경우 강제로 닫아주는 로직
                json_str = json_str.rsplit(',', 1)[0] + "}"
                try:
                    parsed_data = json.loads(json_str, strict=False)
                except:
                    pass

        # 안전망 (키 누락 시 빈 배열 보장)
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key not in parsed_data or not isinstance(parsed_data.get(key), dict):
                parsed_data[key] = {"data": []}
            if "data" not in parsed_data[key] or not isinstance(parsed_data[key]["data"], list):
                parsed_data[key]["data"] = []

        my_bar.empty()
        return {"parsed": parsed_data, "raw": raw_text}

    except Exception as e:
        print("Analysis Error:", e)
        st.error(f"데이터 분석 중 오류 발생: {e}")
        fallback_data = {
            "scores": {
                "manager_score": {"score": 0, "grade": "F"}, "prevention_score": {"score": 0, "grade": "F"},
                "ldar_score": {"score": 0, "grade": "F"}, "record_score": {"score": 0, "grade": "F"},
                "overall_score": {"score": 0, "grade": "F"}
            },
            "manager": {"data": []}, "prevention": {"data": []}, "process_emission": {"data": []}, "ldar": {"data": []},
            "risk_matrix": [], "improvement_roadmap": [],
            "overall_opinion": f"AI 분석 중 에러가 발생했습니다.\n에러 내용: {str(e)}"
        }
        my_bar.empty()
        return {"parsed": fallback_data, "raw": str(e)}
