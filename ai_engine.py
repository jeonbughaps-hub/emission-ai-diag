import os
import fitz
import google.generativeai as genai
import json
import streamlit as st
from datetime import datetime
import tempfile
import time
import warnings
from google.generativeai.types import HarmCategory, HarmBlockThreshold

warnings.filterwarnings("ignore", category=FutureWarning)

KB_DIRECTORY = "knowledge_base/"

def get_model(): 
    # 최신 모델 사용 및 JSON 포맷 강제
    return genai.GenerativeModel(
        "gemini-2.0-flash",
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.0,
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
    # (벡터 DB 로직 생략 없이 그대로 유지)
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
    # 하이브리드 처리를 위해 원본을 그대로 통과시킵니다.
    return pdf_list

def analyze_log_compliance(pdf_list, user_industry: str, vector_db):
    if not os.environ.get("GOOGLE_API_KEY") or not pdf_list: 
        return {"parsed": {}, "raw": ""}

    from utils import get_limit_ppm
    model = get_model()
    limit_text = get_limit_ppm(user_industry)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # ★ 핵심 1: 유해 화학물질/누출 용어로 인한 AI 답변 차단(에러)을 막기 위해 모든 안전 필터 해제
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }

    rag_context = ""
    if vector_db:
        try:
            docs = vector_db.similarity_search(f"{user_industry} 시설관리기준", k=2)
            rag_context = "\n".join([d.page_content for d in docs])
        except: pass

    my_bar = st.progress(0.1, text="문서 유형(텍스트/스캔본)을 분석 중입니다...")
    
    # =====================================================================
    # ★ 핵심 2: 하이브리드 문서 인식 (전자문서 vs 스캔문서)
    # =====================================================================
    all_extracted_text = ""
    total_pages = 0
    
    for name, fbytes in pdf_list:
        try:
            fbytes.seek(0)
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            total_pages += len(doc)
            for page in doc:
                all_extracted_text += page.get_text("text") + "\n"
            doc.close()
        except Exception as e:
            print("PDF Text Extraction Error:", e)

    # 텍스트가 충분히 많으면(1000자 이상) 굳이 비전(Vision)을 쓰지 않고 텍스트로 즉각 분석!
    is_text_pdf = len(all_extracted_text.strip()) > 1000
    
    gfiles = []
    ai_inputs = []

    if is_text_pdf:
        my_bar.progress(0.3, text="⚡ 전자 문서가 감지되었습니다! 초고속 텍스트 분석을 시작합니다.")
        # 너무 길면 토큰 제한에 걸리므로 핵심 구간만 자르기
        ai_inputs = [f"[문서 원문 데이터]\n{all_extracted_text[:800000]}"]
    else:
        my_bar.progress(0.3, text="📷 스캔 문서가 감지되었습니다. 구글 비전 서버로 전송합니다... (약 1분 소요)")
        for name, fbytes in pdf_list:
            try:
                fbytes.seek(0)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(fbytes.read())
                    tmp_path = tmp.name
                gfile = genai.upload_file(path=tmp_path, display_name=name)
                
                wait_count = 0
                while gfile.state.name == "PROCESSING" and wait_count < 30:
                    time.sleep(2)
                    gfile = genai.get_file(gfile.name)
                    wait_count += 1
                if gfile.state.name == "ACTIVE":
                    gfiles.append(gfile)
                os.remove(tmp_path)
            except Exception as e:
                print("Upload Error:", e)
        ai_inputs = gfiles

    if not ai_inputs:
        my_bar.empty()
        return {"parsed": {}, "raw": "No Data to Process"}

    my_bar.progress(0.6, text=f"🚀 AI가 방대한 데이터를 100% 정밀 분석 중입니다...")

    prompt = f"""당신은 환경부 소속 '비산배출시설 기술진단 전문관'입니다.
첨부된 운영기록부 데이터를 완벽하게 분석하여 JSON으로 추출하세요.
업종 기준: {limit_text}

[임무 및 규칙]
1. manager: "성명(관리담당자)" 란에서 정보를 추출하세요.
2. prevention: 방지시설 운영/측정 기록을 찾아 추출하세요. (농도가 기준을 초과하면 result를 "부적합"으로 기재)
3. ldar: "비산누출시설 측정결과" 표를 요약하세요. 
   ★절대 규칙★: 점검 포인트(행)가 수백 개라도 일일이 배열에 넣지 마세요! 전체 행 개수를 세어 `target_count`에 합산하고, 기준치를 초과한 개수만 `leak_count`에 적어 단 1개의 요약된 결과만 반환하세요.
4. scores: 데이터가 정상적으로 존재하면 90~100점(A등급)을 부여하세요.
5. overall_opinion: 500자 이상 공공기관 보고서 톤으로 종합 평가를 작성하세요. (줄바꿈 `\\n` 필수)

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":95, "grade":"A"}}, "overall_score": {{"score":97, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "날짜", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "날짜", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "요약된 총 개수", "leak_count": "초과 건수", "leak_rate": "0%", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "방지시설 관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검", "expected_effect": "안정화"}} ],
  "overall_opinion": "여기에 종합 의견 상세 작성 (줄바꿈 \\n 사용)"
}}
"""
    try:
        # 안전 필터를 해제하고 요청 전송!
        response = model.generate_content(
            [prompt, *ai_inputs], 
            safety_settings=safety_settings,
            request_options={"timeout": 300}
        )
        
        # 확실한 JSON 파싱 방어 로직
        raw_text = response.text.strip()
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()
            
        parsed_data = json.loads(raw_text, strict=False)
        
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key not in parsed_data or not isinstance(parsed_data.get(key), dict):
                parsed_data[key] = {"data": []}
            if "data" not in parsed_data[key] or not isinstance(parsed_data[key]["data"], list):
                parsed_data[key]["data"] = []

        my_bar.empty()
        return {"parsed": parsed_data, "raw": raw_text}

    except Exception as e:
        # ★ 화면에 진짜 원인(에러 메시지)을 붉은색으로 명확하게 띄워줍니다!
        st.error(f"🚨 AI 데이터 추출 실패! 상세 원인: {str(e)}")
        fallback_data = {
            "scores": {
                "manager_score": {"score": 0, "grade": "F"}, "prevention_score": {"score": 0, "grade": "F"},
                "ldar_score": {"score": 0, "grade": "F"}, "record_score": {"score": 0, "grade": "F"},
                "overall_score": {"score": 0, "grade": "F"}
            },
            "manager": {"data": []}, "prevention": {"data": []}, "process_emission": {"data": []}, "ldar": {"data": []},
            "risk_matrix": [], "improvement_roadmap": [],
            "overall_opinion": f"데이터 추출 중 에러가 발생했습니다. (사유: {str(e)})"
        }
        my_bar.empty()
        return {"parsed": fallback_data, "raw": str(e)}
    finally:
        # 구글 서버 파일 청소
        for gf in gfiles:
            try: genai.delete_file(gf.name)
            except: pass
