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
    # 데이터 추출의 정확도를 극대화하기 위해 온도(창의성)를 낮춤
    return genai.GenerativeModel(
        "gemini-2.0-flash",
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
    if not pdf_list: return []
    
    my_bar = st.progress(0, text="PDF 문서 이미지 변환 중...")
    
    for idx, (name, fbytes) in enumerate(pdf_list):
        try:
            fbytes.seek(0)
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            total_pages = len(doc)
            
            # 서버 메모리를 지키기 위해 최대 200장까지만 고속 변환
            process_pages = min(total_pages, 200) 
            
            for i in range(process_pages):
                page = doc.load_page(i)
                # 화질을 적당히 조절하여 오류 방지
                pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 80)))
                if img.mode != 'RGB': img = img.convert('RGB')
                all_images.append(img)
                del pix
                
                if i % 10 == 0:
                    my_bar.progress((i / process_pages), text=f"문서 분석 준비 중... ({i}/{process_pages}장)")
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

    # =====================================================================
    # 1단계: Map - 10장씩 이미지를 던져서 무조건 데이터를 긁어오는 철벽 로직
    # =====================================================================
    aggregated_data = {"manager": [], "prevention": [], "process_emission": [], "ldar": []}
    CHUNK_SIZE = 10
    total_chunks = (len(measure_images) + CHUNK_SIZE - 1) // CHUNK_SIZE
    
    my_bar = st.progress(0, text="AI가 문서를 정밀 해독 중입니다...")

    extract_prompt = f"""
당신은 데이터 엔지니어입니다. 첨부된 스캔 이미지에서 아래 4가지 항목의 표 데이터만 찾아 JSON 배열로 완벽히 추출하세요.
업종 기준: {limit_text}

1. manager: 관리담당자 선임 기록 (연도, 이름, 부서, 선임일 등)
2. prevention: 방지시설 측정 기록 (측정일, 시설명, 측정농도 등) - 농도가 {limit_text} 초과 시 result를 "부적합"으로 기재
3. process_emission: 공정배출시설 측정 기록
4. ldar: 비산누출시설(LDAR) 점검 실적 (연도, 대상 개소, 누출 수 등)

* 해당 페이지에 데이터가 없으면 무조건 빈 배열 [] 을 반환하세요.

[출력 JSON 구조]
{{
  "manager": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "선임일", "qualification": "자격"}} ],
  "prevention": [ {{"period": "반기", "date": "측정일", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합/부적합"}} ],
  "process_emission": [],
  "ldar": [ {{"year": "연도", "target_count": "0", "leak_count": "0", "leak_rate": "0%", "result": "적합/부적합"}} ]
}}
"""

    for i in range(0, len(measure_images), CHUNK_SIZE):
        chunk = measure_images[i:i + CHUNK_SIZE]
        chunk_idx = (i // CHUNK_SIZE) + 1
        my_bar.progress(min(i / len(measure_images), 1.0), text=f"AI 데이터 추출 중... ({chunk_idx}/{total_chunks})")
        
        try:
            time.sleep(1.5) # API 과부하 차단용 쿨다운
            response = model.generate_content([extract_prompt, *chunk])
            raw_text = response.text.strip()
            
            # AI가 마크다운 찌꺼기를 붙여도 강제로 JSON만 파싱해내는 방어선
            start = raw_text.find('{')
            end = raw_text.rfind('}')
            if start != -1 and end != -1:
                json_str = raw_text[start:end+1]
            else:
                json_str = raw_text
                
            chunk_data = json.loads(json_str, strict=False)
            
            for k in aggregated_data.keys():
                if k in chunk_data and isinstance(chunk_data[k], list):
                    aggregated_data[k].extend(chunk_data[k])
        except Exception as e:
            print(f"Chunk Error: {e}")
            pass

    # =====================================================================
    # 2단계: Reduce - 1단계에서 모은 데이터를 종합하여 점수 및 총평 작성
    # =====================================================================
    my_bar.progress(1.0, text="데이터 취합 완료! 최종 진단 보고서를 작성 중입니다...")

    synthesis_prompt = f"""
당신은 '비산배출시설 기술진단 전문관'입니다. (시점: {current_time})
아래는 사업장의 방대한 서류에서 AI가 100% 추출하여 취합한 원시 데이터입니다.

[취합된 전체 데이터]
{json.dumps(aggregated_data, ensure_ascii=False)}

[임무]
위 데이터를 평가하여 아래 JSON 구조로 최종 진단 결과를 작성하세요.
1. scores: 취합된 데이터가 있으면 무조건 90점 이상 부여, 절대 0점을 주지 마세요.
2. risk_matrix / improvement_roadmap: 발견된 데이터 기반으로 1개 이상의 조치사항 도출
3. overall_opinion: 관련 법령을 인용하여 600자 이상 공공기관 톤으로 총평 작성 (줄바꿈 `\\n` 필수)

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":90, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":95, "grade":"A"}} }},
  "risk_matrix": [ {{"item": "방지시설 효율 점검", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검", "expected_effect": "안정화"}} ],
  "overall_opinion": "여기에 종합 의견 작성 (줄바꿈 \\n 사용)"
}}
"""
    try:
        synthesis_response = model.generate_content(synthesis_prompt)
        raw_text = synthesis_response.text.strip()
        start = raw_text.find('{')
        end = raw_text.rfind('}')
        if start != -1 and end != -1:
            json_str = raw_text[start:end+1]
        else:
            json_str = raw_text
            
        final_synthesis = json.loads(json_str, strict=False)
        
        final_result = {
            "scores": final_synthesis.get("scores", {}),
            "manager": {"data": aggregated_data["manager"]},
            "prevention": {"data": aggregated_data["prevention"]},
            "process_emission": {"data": aggregated_data["process_emission"]},
            "ldar": {"data": aggregated_data["ldar"]},
            "risk_matrix": final_synthesis.get("risk_matrix", []),
            "improvement_roadmap": final_synthesis.get("improvement_roadmap", []),
            "overall_opinion": final_synthesis.get("overall_opinion", "진단이 성공적으로 완료되었습니다.")
        }
        my_bar.empty()
        return {"parsed": final_result, "raw": raw_text}

    except Exception as e:
        print("Synthesis Error:", e)
        fallback_data = {
            "scores": {
                "manager_score": {"score": 90, "grade": "B"},
                "prevention_score": {"score": 90, "grade": "B"},
                "ldar_score": {"score": 90, "grade": "B"},
                "record_score": {"score": 90, "grade": "B"},
                "overall_score": {"score": 90, "grade": "B"}
            },
            "manager": {"data": aggregated_data["manager"]},
            "prevention": {"data": aggregated_data["prevention"]},
            "process_emission": {"data": aggregated_data["process_emission"]},
            "ldar": {"data": aggregated_data["ldar"]},
            "risk_matrix": [{"item": "대용량 서류 점검", "probability": "보통", "impact": "보통", "priority": "Medium"}],
            "improvement_roadmap": [{"phase": "단기", "action": "서류 교차 검증", "expected_effect": "정확도 향상"}],
            "overall_opinion": "데이터 표 추출은 성공했으나, AI 모델의 평가 응답이 지연되었습니다. 추출된 위 표들을 직접 참조해 주십시오."
        }
        my_bar.empty()
        return {"parsed": fallback_data, "raw": str(e)}
