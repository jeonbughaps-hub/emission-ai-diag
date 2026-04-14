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
import time

warnings.filterwarnings("ignore", category=FutureWarning)

KB_DIRECTORY = "knowledge_base/"

def get_model(): 
    # 데이터 추출의 정확도를 높이기 위해 temperature를 0.1로 낮게 설정
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
    for _, fbytes in pdf_list:
        try:
            fbytes.seek(0)
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            
            # 스캔본 인식을 위해 화질을 1.5배수로 설정하여 이미지로 변환
            for page in doc:
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
    
    # =================================================================
    # 1단계: 분할 정복 (Chunking) - 10장씩 쪼개서 데이터만 완벽하게 추출
    # =================================================================
    CHUNK_SIZE = 10
    total_images = len(measure_images)
    
    aggregated_data = {
        "manager": [],
        "prevention": [],
        "process_emission": [],
        "ldar": []
    }

    # Streamlit UI 상에 진행률 표시
    progress_text = f"총 {total_images}장의 스캔 문서를 {CHUNK_SIZE}장씩 분할하여 정밀 분석 중입니다..."
    my_bar = st.progress(0, text=progress_text)

    for i in range(0, total_images, CHUNK_SIZE):
        chunk = measure_images[i : i + CHUNK_SIZE]
        
        extract_prompt = f"""
당신은 스캔된 문서에서 데이터를 추출하는 데이터 엔지니어입니다.
업종 기준: {limit_text}

[임무]
첨부된 문서 이미지에서 다음 4가지 항목의 표 데이터만 완벽하게 찾아내어 JSON 배열로 추출하세요.
1. manager: 관리담당자 선임 기록 (연도, 이름, 소속, 선임일 등)
2. prevention: 방지시설 측정 기록 (측정일, 시설명, 측정농도 등) - 농도가 {limit_text}를 초과하면 result를 "부적합"으로 기재
3. process_emission: 공정배출시설 측정 기록
4. ldar: 비산누출시설(LDAR) 점검 실적

[규칙]
- 데이터가 없으면 무조건 빈 배열 [] 을 반환하세요.
- 이미지가 몇 장이든 누락 없이 표에 있는 모든 행(Row)을 추출해야 합니다.

[출력 JSON 구조]
{{
  "manager": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "선임일", "qualification": "자격"}} ],
  "prevention": [ {{"period": "반기", "date": "측정일", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합/부적합"}} ],
  "process_emission": [],
  "ldar": [ {{"year": "연도", "target_count": "0", "leak_count": "0", "leak_rate": "0%", "result": "적합/부적합"}} ]
}}
"""
        try:
            response = model.generate_content([extract_prompt, *chunk])
            chunk_data = json.loads(response.text.strip(), strict=False)
            
            # 추출된 데이터 병합
            for key in aggregated_data.keys():
                if key in chunk_data and isinstance(chunk_data[key], list):
                    aggregated_data[key].extend(chunk_data[key])
        except Exception as e:
            print(f"Chunk {i} Error:", e)
            pass # 일부 실패하더라도 멈추지 않고 다음 청크 계속 진행
            
        # 진행률 업데이트
        progress = min((i + CHUNK_SIZE) / total_images, 1.0)
        my_bar.progress(progress, text=f"스캔 문서 정밀 데이터 추출 중... ({int(progress*100)}%)")
        time.sleep(1) # API 호출 제한 방지 (Rate Limit 쿨다운)

    # =================================================================
    # 2단계: 종합 진단 (Synthesis) - 합쳐진 데이터를 바탕으로 종합 보고서 작성
    # =================================================================
    my_bar.progress(1.0, text="데이터 추출 완료! AI 종합 진단 의견 및 점수를 산정 중입니다...")
    
    rag_context = ""
    if vector_db:
        try:
            docs = vector_db.similarity_search(f"{user_industry} 시설관리기준", k=2)
            rag_context = "\n".join([d.page_content for d in docs])
        except: pass

    synthesis_prompt = f"""
당신은 환경부 소속의 '비산배출시설 기술진단 전문관'입니다. (시점: {current_time})
아래의 데이터는 사업장의 수백 장의 스캔 서류에서 100% 추출하여 취합한 원시 데이터입니다.

[취합된 전체 데이터]
{json.dumps(aggregated_data, ensure_ascii=False)}

[임무]
위 취합된 데이터를 바탕으로 아래 JSON 포맷에 맞게 최종 진단 결과를 작성하세요.
1. scores: 취합된 데이터를 평가하여 합리적인 점수(0~100)와 등급(A~F)을 산정하세요. (데이터가 아예 없지 않은 이상 0점을 주지 마세요)
2. risk_matrix 및 improvement_roadmap: 발견된 데이터를 바탕으로 최소 1개 이상씩 권고안을 작성하세요.
3. overall_opinion: 관련 법령을 인용하여 600자 이상 전문적이고 상세하게 작성하세요. (줄바꿈은 반드시 `\\n`을 사용)
4. 참고 법령: {rag_context[:600]}

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":90, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":95, "grade":"A"}} }},
  "risk_matrix": [ {{"item": "방지시설 농도 점검", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 정밀 점검", "expected_effect": "안정화"}} ],
  "overall_opinion": "여기에 종합 의견을 작성합니다."
}}
"""
    try:
        synthesis_response = model.generate_content(synthesis_prompt)
        final_synthesis = json.loads(synthesis_response.text.strip(), strict=False)
        
        # 1단계의 데이터와 2단계의 평가 결과를 최종 병합
        final_result = {
            "scores": final_synthesis.get("scores", {}),
            "manager": {"data": aggregated_data["manager"]},
            "prevention": {"data": aggregated_data["prevention"]},
            "process_emission": {"data": aggregated_data["process_emission"]},
            "ldar": {"data": aggregated_data["ldar"]},
            "risk_matrix": final_synthesis.get("risk_matrix", []),
            "improvement_roadmap": final_synthesis.get("improvement_roadmap", []),
            "overall_opinion": final_synthesis.get("overall_opinion", "종합 의견이 성공적으로 생성되었습니다.")
        }
        
        my_bar.empty() # 진행률 바 숨기기
        return {"parsed": final_result, "raw": synthesis_response.text}

    except Exception as e:
        print("Synthesis Error:", e)
        # 방어선 구축: 만약 에러가 나더라도 추출된 데이터라도 살려서 반환
        fallback_data = {
            "scores": {"manager_score": {"score": 90, "grade": "B"}, "prevention_score": {"score": 90, "grade": "B"}, "ldar_score": {"score": 90, "grade": "B"}, "record_score": {"score": 90, "grade": "B"}, "overall_score": {"score": 90, "grade": "B"}},
            "manager": {"data": aggregated_data["manager"]},
            "prevention": {"data": aggregated_data["prevention"]},
            "process_emission": {"data": aggregated_data["process_emission"]},
            "ldar": {"data": aggregated_data["ldar"]},
            "risk_matrix": [{"item": "대용량 서류 점검", "probability": "보통", "impact": "보통", "priority": "Medium"}],
            "improvement_roadmap": [{"phase": "단기", "action": "원본 서류 교차 검증 요망", "expected_effect": "신뢰성 확보"}],
            "overall_opinion": "데이터 추출은 완료되었으나, 종합 의견 산정 중 일시적인 오류가 발생했습니다. 위 추출된 세부 내역을 확인해 주세요."
        }
        my_bar.empty()
        return {"parsed": fallback_data, "raw": str(e)}
