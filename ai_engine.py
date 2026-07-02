import os
import fitz
from google import genai
from google.genai import types
from PIL import Image
import io
import json
import re
import streamlit as st
from datetime import datetime
import gc 
import warnings
import zipfile 

# 🚨 RAG(지식베이스) 연동을 위한 LangChain 라이브러리 추가
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS

warnings.filterwarnings("ignore", category=FutureWarning)

# 지식베이스(벡터 DB)가 영구 저장될 서버 내 폴더명
FAISS_DB_DIR = "faiss_vector_db"

# =====================================================================
# 🧠 1. 지식베이스 구축 및 로드 (RAG 시스템)
# =====================================================================
def build_vector_db(uploaded_kb_file):
    """관리자가 업로드한 ZIP(법규/매뉴얼)을 분석하여 서버 디스크에 영구 저장합니다."""
    if not uploaded_kb_file: return False
    
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key: return False

    kb_text = ""
    try:
        # ZIP 파일 내부의 모든 PDF 텍스트 추출
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
        # 텍스트를 의미 단위로 분할 (Chunking)
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_text(kb_text)

        # 임베딩(벡터화) 후 FAISS DB 생성
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
        vector_db = FAISS.from_texts(chunks, embeddings)
        
        # 🚨 핵심: 생성된 DB를 서버 하드디스크에 영구 저장!
        vector_db.save_local(FAISS_DB_DIR)
        return True
    except Exception as e:
        st.error(f"벡터 DB 생성/저장 실패: {e}")
        return False

def load_vector_db():
    """일반 사용자가 진단 시 서버 디스크에 저장된 지식베이스를 조용히 불러옵니다."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key: return None
    
    # 저장된 폴더가 존재하면 로드
    if os.path.exists(FAISS_DB_DIR):
        try:
            embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
            # allow_dangerous_deserialization=True 는 로컬에 직접 저장한 DB를 읽을 때 필요한 보안 옵션
            vector_db = FAISS.load_local(FAISS_DB_DIR, embeddings, allow_dangerous_deserialization=True)
            return vector_db
        except:
            return None
    return None

# =====================================================================
# 📄 2. 사용자 업로드 문서 처리 및 AI 진단 (기존 로직 유지)
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
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not measure_images: return {"parsed": {}, "raw": ""}
    client = genai.Client(api_key=api_key)
    
    industry_str = str(user_industry).upper()
    if any(x in industry_str for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]):
        limit_val = 100
        limit_text = "100ppm"
    else:
        limit_val = 50
        limit_text = "50ppm"
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 🚨 RAG: 지식베이스에서 업종 및 규제 관련 법규 문맥 검색
    retrieved_knowledge = ""
    if vector_db is not None:
        try:
            search_query = f"비산배출시설 {user_industry} 방지시설 관리기준 및 LDAR 누출 점검 행정처분 규정"
            docs = vector_db.similarity_search(search_query, k=3) # 상위 3개 핵심 문서 검색
            retrieved_knowledge = "\n".join([doc.page_content for doc in docs])
        except:
            retrieved_knowledge = ""

    prompt = f"""당신은 환경부 비산배출시설 기술진단 전문 엔진입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[★ 지식베이스 (참고 법규 및 환경부 매뉴얼) ★]
{retrieved_knowledge if retrieved_knowledge else "제공된 지식베이스 없음. 기본 지식 활용."}

[★ 최우선 지시사항 : 대규모 문서 100% 전수조사 및 요약/누락 절대 금지 ★]
1. AI 분석 태도 (Anti-Laziness):
   - 문서가 수십 페이지에 달하더라도 절대 중간에 분석을 멈추거나, 임의로 데이터를 요약, 샘플링, 생략하지 마세요. 
   - 마지막 페이지의 마지막 표까지 100% 전수 조사하여 데이터를 긁어모아야 합니다.

2. 방지시설 농도 (prevention) 무한 추출 규칙:
   - 여러 연도와 여러 반기에 걸쳐 측정된 '모든' 데이터를 빠짐없이 추출하여 배열에 담으세요. (단, 비전테크, 코엔라이프 등 외부업체명은 시설명에서 제외)
   - 결과값이 '34.0~287.0' 처럼 범위로 되어있어도 절대 빼먹지 말고 그대로 추출하세요.

3. LDAR 누출 점검 (ldar) 다년도 전수 카운팅 규칙:
   - 제공된 문서에는 '여러 연도'의 점검 기록이 혼재되어 있습니다. 각 '연도별'로 실제 측정값(농도)이 기재된 줄(Row)의 개수를 모든 페이지에서 찾아 누적 합산하세요.
   - 앞 페이지의 요약표가 비어있더라도, 뒷부분 원시 데이터 표에 있는 측정 행(Row) 숫자를 직접 끝까지 세어 target_count에 기입하세요.

[전문 종합 의견 작성 지침]
- 4가지 소제목을 사용하여 800자 내외로 상세하게 작성하세요.
- 🚨 반드시 위 [★ 지식베이스 ★]에 제공된 법규 내용과 매뉴얼 지침을 인용하여, 객관적이고 전문적인 근거를 바탕으로 진단 의견과 로드맵을 작성하세요.

[출력 JSON 구조] 
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"B"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "prevention": {{ "data": [ {{"period": "구분", "date": "측정일자(YYYY-MM-DD)", "facility": "순수 방지시설명", "value": "농도값", "limit": "{limit_text}", "result": "적합/부적합"}} ] }},
  "ldar": {{ "data": [ {{"year": "연도(YYYY)", "target_count": "실제측정된개소수(숫자)", "leak_count": "0", "leak_rate": "0%", "recheck_done": "이행완료", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "시설관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검 강화", "expected_effect": "효율 안정화"}} ],
  "overall_opinion": "여기에 소제목을 포함하여 상세히 작성하세요."
}}
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt] + measure_images,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0, 
                max_output_tokens=8192,
                safety_settings=[types.SafetySetting(category=c, threshold="BLOCK_NONE") for c in ["HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
            )
        )
        
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text.replace("```json", "", 1)
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        parsed_data = json.loads(raw_text, strict=False)
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        try:
            parsed_data = json.loads(re.search(r'\{.*\}', raw_text, re.DOTALL).group(0), strict=False)
            return {"parsed": parsed_data, "raw": raw_text}
        except Exception as e2:
            return {"parsed": {}, "raw": str(e)}

def generate_advanced_air_advice(station_name: str, pm10_val: str, o3_val: str):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key: return "대기질 정보를 불러올 수 없습니다."
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
당신은 국립환경과학원 수준의 대기환경 전문 연구원입니다.
관할 측정소({station_name})의 현재 실시간 대기질은 미세먼지(PM10): {pm10_val} ㎍/m³, 오존(O3): {o3_val} ppm 입니다.
이 사업장은 '유기용제(VOCs)'를 다량 취급하는 비산배출시설입니다.

아래 3가지 소제목을 사용하여 **총 800자 분량**의 아주 깊이 있고 전문적인 '환경 관리 지침'을 작성하세요.

【1. 지역 대기질 현황 및 광화학적 영향 분석】
- 현재 지역 오존/미세먼지 수치의 위험도를 평가.
- 사업장 배출 VOCs가 질소산화물(NOx)과 광화학 반응을 일으켜 오존(O3)을 생성하고, 2차 유기 에어로졸(SOA)로 변환되어 미세먼지를 가중시킨다는 점을 과학적으로 설명.

【2. 현장 비산배출원 선제적 통제 가이드】
- 오후 피크타임(14~16시) 유기용제 취급 공정 가동률 조정, 옥외 하역 밀폐 조건, 혼합 과정에서의 원천적 누출 차단 등 구체적 가이드 제공.

【3. 방지시설 및 LDAR 연계 집중 관리 방안】
- 활성탄 흡착탑 등 방지시설 처리 효율 최적화를 위한 차압 관리 및 교체 주기 준수.
- 회전/연결 기기(플랜지, 밸브 등) 선제적 LDAR(누출탐지 및 보수) 강화 지시.
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.4, 
                max_output_tokens=2048
            )
        )
        return response.text.strip()
    except Exception:
        return "대기질 API 연동 지연으로 상세 분석을 생략합니다. 사업장 자체적인 VOCs 누출 점검을 강화해 주시기 바랍니다."
