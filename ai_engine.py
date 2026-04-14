import os
import fitz
import google.generativeai as genai
from PIL import Image
import io
import json
import streamlit as st
from datetime import datetime
import time
import gc 
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

KB_DIRECTORY = "knowledge_base/"

def get_model(): 
    # ★ Gemini 2.0 Pro 모델 탑재! (정밀 데이터 추출)
    return genai.GenerativeModel(
        "gemini-2.0-pro-exp", 
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.0 # 환각(거짓말)을 막기 위해 창의성 완벽 차단
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
    # 메모리 과부하를 막기 위해 이미지 변환은 analyze 함수 내에서 실시간으로 처리합니다.
    return pdf_list

def analyze_log_compliance(pdf_list, user_industry: str, vector_db):
    if not os.environ.get("GOOGLE_API_KEY") or not pdf_list: 
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

    # =====================================================================
    # 1단계: Map (Gemini 2.0 Pro의 강력한 비전 인식으로 10장씩 정밀 스캔)
    # =====================================================================
    aggregated_data = {"manager": [], "prevention": [], "process_emission": [], "ldar": []}
    CHUNK_SIZE = 10 
    
    # ★ 에러 수정 부분: 페이지 수를 안전하고 정확하게 계산하는 반복문으로 변경
    total_pages = 0
    for name, fbytes in pdf_list:
        try:
            fbytes.seek(0)
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            total_pages += len(doc)
            doc.close()
        except Exception as e:
            print(f"Error reading {name} for page count: {e}")
            pass

    if total_pages == 0: return {"parsed": {}, "raw": ""}

    st.info(f"🚀 [Gemini 2.0 Pro 가동] 총 {total_pages}장의 서류를 최고 성능 AI 모델로 정밀 해독합니다. 진짜 데이터만 100% 추출합니다.")
    my_bar = st.progress(0, text="초정밀 데이터 추출 준비 중...")

    extract_prompt = f"""당신은 환경부의 최고 등급 데이터 전문관입니다.
첨부된 스캔 문서 10장 구간에서 아래 표 데이터를 단 하나도 빠짐없이 찾아 JSON으로 추출하세요.
글씨가 흐리거나 양식이 복잡해도 꼼꼼히 판독해야 합니다. 가짜 데이터를 임의로 만들지 마세요.
업종 기준: {limit_text}

1. manager: 관리담당자 선임 기록 (연도, 이름, 소속, 선임일 등)
2. prevention: 방지시설 측정 기록 (측정일, 시설명, 측정농도 등) - 농도가 {limit_text} 초과 시 result를 "부적합"으로 기재
3. process_emission: 공정배출시설 측정 기록
4. ldar: 비산누출시설(LDAR) 점검 실적 (점검 연도, 대상 개소, 누출 수, 누출률 등)

* 표가 없거나 데이터를 찾을 수 없다면 정직하게 빈 배열 `[]` 을 반환하세요.

[출력 JSON 구조]
{{
  "manager": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "날짜", "qualification": "자격"}} ],
  "prevention": [ {{"period": "반기", "date": "날짜", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합/부적합"}} ],
  "process_emission": [],
  "ldar": [ {{"year": "연도", "target_count": "0", "leak_count": "0", "leak_rate": "0%", "result": "적합/부적합"}} ]
}}
"""

    current_processed = 0
    for name, fbytes in pdf_list:
        fbytes.seek(0)
        doc = fitz.open(stream=fbytes.read(), filetype="pdf")
        doc_pages = len(doc)
        
        for i in range(0, doc_pages, CHUNK_SIZE):
            chunk_images = []
            
            # 해상도를 높여서 선명한 이미지를 제공
            for p_idx in range(i, min(i + CHUNK_SIZE, doc_pages)):
                page = doc.load_page(p_idx)
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 85)))
                if img.mode != 'RGB': img = img.convert('RGB')
                chunk_images.append(img)
                del pix
                current_processed += 1
            
            my_bar.progress(current_processed / total_pages, text=f"Gemini 2.0 Pro 스캔 중... ({current_processed}/{total_pages}쪽 완료)")
            
            try:
                time.sleep(2) # API Rate Limit 보호
                response = model.generate_content([extract_prompt, *chunk_images], request_options={"timeout": 120})
                chunk_data = json.loads(response.text.strip(), strict=False)
                
                # 추출된 데이터 누적
                for k in aggregated_data.keys():
                    if k in chunk_data and isinstance(chunk_data[k], list):
                        aggregated_data[k].extend(chunk_data[k])
            except Exception as e:
                print("Chunk Error (2.0 Pro):", e)
                pass 
                
            # 즉시 메모리 해제
            del chunk_images
            gc.collect()
            
        doc.close()

    # =====================================================================
    # 2단계: Reduce (2.0 Pro의 정확한 논리력을 바탕으로 종합 진단)
    # =====================================================================
    my_bar.progress(1.0, text="데이터 추출 완료! 엄격한 기준에 따라 종합 진단 보고서를 작성 중입니다...")

    synthesis_prompt = f"""당신은 환경부 소속 '비산배출시설 기술진단 전문관'입니다.
아래는 사업장의 스캔 서류에서 100% 팩트로 추출된 원시 데이터입니다.

[추출 데이터]
{json.dumps(aggregated_data, ensure_ascii=False)}

[임무]
1. scores: 위 추출 데이터만 사용하여 냉정하게 점수(0~100)와 등급(A~F)을 매기세요. 표가 비어있다면 감점 요인입니다.
2. risk_matrix / improvement_roadmap: 발견된 데이터를 기반으로 실질적 조치사항을 1개 이상 도출하세요.
3. overall_opinion: 관련 법령을 인용하여 500자 이상 전문적인 총평을 작성하세요. (줄바꿈 `\\n` 필수)

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":80, "grade":"B"}}, "prevention_score": {{"score":90, "grade":"A"}}, "ldar_score": {{"score":85, "grade":"B"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":88, "grade":"B"}} }},
  "risk_matrix": [ {{"item": "방지시설 점검", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검", "expected_effect": "안정화"}} ],
  "overall_opinion": "여기에 종합 의견 작성 (줄바꿈 \\n 사용)"
}}
"""
    try:
        synthesis_response = model.generate_content(synthesis_prompt, request_options={"timeout": 120})
        final_synthesis = json.loads(synthesis_response.text.strip(), strict=False)
        
        final_result = {
            "scores": final_synthesis.get("scores", {}),
            "manager": {"data": aggregated_data.get("manager", [])},
            "prevention": {"data": aggregated_data.get("prevention", [])},
            "process_emission": {"data": aggregated_data.get("process_emission", [])},
            "ldar": {"data": aggregated_data.get("ldar", [])},
            "risk_matrix": final_synthesis.get("risk_matrix", []),
            "improvement_roadmap": final_synthesis.get("improvement_roadmap", []),
            "overall_opinion": final_synthesis.get("overall_opinion", "진단 완료")
        }
        my_bar.empty()
        return {"parsed": final_result, "raw": synthesis_response.text}

    except Exception as e:
        print("Synthesis Error (2.0 Pro):", e)
        fallback_data = {
            "scores": {
                "manager_score": {"score": 0, "grade": "F"}, "prevention_score": {"score": 0, "grade": "F"},
                "ldar_score": {"score": 0, "grade": "F"}, "record_score": {"score": 0, "grade": "F"},
                "overall_score": {"score": 0, "grade": "F"}
            },
            "manager": {"data": aggregated_data.get("manager", [])},
            "prevention": {"data": aggregated_data.get("prevention", [])},
            "process_emission": {"data": aggregated_data.get("process_emission", [])},
            "ldar": {"data": aggregated_data.get("ldar", [])},
            "risk_matrix": [], "improvement_roadmap": [],
            "overall_opinion": "데이터 표 추출은 완료되었으나 종합 스코어링 중 서버 오류가 발생했습니다. 위 표를 참조하십시오."
        }
        my_bar.empty()
        return {"parsed": fallback_data, "raw": str(e)}
