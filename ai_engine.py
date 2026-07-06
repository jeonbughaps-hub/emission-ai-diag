import os
import fitz
import google.generativeai as genai
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

# =====================================================================
# 🧠 1. 지식베이스 구축 및 로드 (RAG 시스템)
# =====================================================================
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

# =====================================================================
# 📄 2. 사용자 업로드 문서 처리 및 AI 진단
# =====================================================================
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
                st.error(f"ZIP 파일 압축 해제 중 오류: {e}")
    return pdf_list

def convert_and_mask_images(pdf_list):
    all_images = []
    my_bar = st.progress(0.1, text="PDF 문서 정밀 스캔 및 텍스트 가독성 복원 중...")
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
    if not api_key: return {"parsed": {}, "raw": "API 키를 확인할 수 없습니다."}
            
    # 안정적인 기존 라이브러리로 초기화
    genai.configure(api_key=api_key)
    
    industry_str = str(user_industry).upper()
    if any(x in industry_str for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]):
        limit_text = "100ppm"
    else:
        limit_text = "50ppm"
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    retrieved_knowledge = ""
    if vector_db is not None:
        try:
            search_query = f"비산배출시설 {user_industry} 방지시설 관리기준 및 행정처분"
            docs = vector_db.similarity_search(search_query, k=3)
            retrieved_knowledge = "\n".join([doc.page_content for doc in docs])
        except:
            retrieved_knowledge = ""

    prompt = f"""당신은 환경부 비산배출시설 기술진단 전문 엔진입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

아래 <지시사항>을 엄격히 준수하여 <출력형식>의 순수 JSON 포맷으로만 답변하세요.

<지시사항>
1. 데이터 100% 전수조사 추출 (가장 최우선 임무)
- 첨부된 문서 이미지 표를 끝까지 읽고 '실제 데이터'를 찾아 배열을 꽉 채워야 합니다.
- 방지시설 농도 (prevention): 제공된 표의 칼럼 중 '측정일시', '시설명', '측정결과 후단'을 모두 추출하세요. (주의: THC 측정기기 정도검사의 기준에서 '결과' 부분은 철저히 제외하고 출력하세요.)
- LDAR 누출 점검 (ldar): 연도별로 실제 점검 측정값이 기록된 행(Row)의 개수를 직접 세어 target_count에 기입하세요.
- 열교환기 판정: 열교환기의 편차가 미확인(공란 등)된 경우 판정은 무조건 '판단불가'로 기재하세요.

2. 종합 의견 작성
- 아래 <지식베이스> 영역의 법규/매뉴얼 내용을 인용하여 전문적인 진단 의견을 800자 내외로 상세히 작성하세요.
</지시사항>

<지식베이스>
{retrieved_knowledge if retrieved_knowledge else "기본 환경 지식 활용"}
</지식베이스>

<출력형식>
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"B"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "실제측정일", "facility": "실제시설명", "value": "실제농도값", "limit": "{limit_text}"}} ] }},
  "ldar": {{ "data": [ {{"year": "실제연도", "target_count": "합산개소", "leak_count": "0", "leak_rate": "0%", "recheck_done": "이행완료", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "시설관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검 강화", "expected_effect": "효율 안정화"}} ],
  "overall_opinion": "여기에 지식베이스를 활용하여 상세히 작성"
}}
</출력형식>
"""
    try:
        # 대규모 문서 전수조사에 가장 강력한 gemini-1.5-pro 모델 사용
        model = genai.GenerativeModel('gemini-1.5-pro')
        response = model.generate_content(
            [prompt] + measure_images,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        
        raw_text = response.text.strip()
        json_prefix = "`" * 3 + "json"
        suffix = "`" * 3
        
        if raw_text.startswith(json_prefix):
            raw_text = raw_text.replace(json_prefix, "", 1)
            if raw_text.endswith(suffix):
                raw_text = raw_text[:-3]
        
        try:
            parsed_data = json.loads(raw_text.strip(), strict=False)
        except Exception:
            parsed_data = json.loads(re.search(r'\{.*\}', raw_text, re.DOTALL).group(0), strict=False)
            
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": f"파싱 에러: {str(e)}"}

def generate_advanced_air_advice(station_name: str, pm10_val: str, o3_val: str):
    time.sleep(3)
    api_key = get_api_key()
    if not api_key: return "대기질 API 키 설정 오류로 상세 분석을 생략합니다."
            
    genai.configure(api_key=api_key)
    
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
        model = genai.GenerativeModel('gemini-1.5-pro')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.4)
        )
        return response.text.strip()
    except Exception:
        return "AI 모델 통신 오류로 전문가 제언 생성을 일시 생략합니다. 자체 점검을 강화해 주시기 바랍니다."
