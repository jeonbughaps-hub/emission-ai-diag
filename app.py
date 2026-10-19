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
import time

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS

from pdf_generator import create_gov_report_pdf

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
                st.error(f"ZIP 압축 해제 중 오류: {e}")
    return pdf_list

def convert_and_mask_images(pdf_list):
    all_images = []
    my_bar = st.progress(0.1, text="PDF 문서 정밀 스캔 중...")
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
    if not api_key: 
        st.error("API 키를 찾을 수 없습니다. Secrets 설정을 확인하세요.")
        return {"parsed": {}, "raw": "API 키 오류"}
            
    client = genai.Client(api_key=api_key)
    
    industry_str = str(user_industry).upper()
    if any(x in industry_str for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]):
        limit_text = "100ppm 미만 또는 저감효율 80% 이상"
        ppm_limit = "100"
        eff_limit = "80"
    else:
        limit_text = "50ppm 미만 또는 저감효율 90% 이상"
        ppm_limit = "50"
        eff_limit = "90"
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    retrieved_knowledge = ""
    if vector_db is not None:
        try:
            search_query = f"비산배출시설 {user_industry} 방지시설 냉각탑 열교환기 관리기준 및 행정처분"
            docs = vector_db.similarity_search(search_query, k=4)
            retrieved_knowledge = "\n".join([doc.page_content for doc in docs])
        except:
            retrieved_knowledge = ""

    prompt = f"""당신은 환경부 비산배출시설 기술진단 전문 AI입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[★ 최우선 지시사항 : 데이터 100% 전수조사 추출 ★]
1. 첨부된 모든 문서/이미지를 스캔하여 아래 데이터를 찾아 배열에 담으세요.
2. 방지시설 농도 (prevention): '측정일시', '시설명', '측정결과 후단' 칼럼의 값을 추출하세요. (THC 측정기기 정도검사 결과는 제외)
   - 🚨 저감효율 예외 판정: 측정값이 {ppm_limit}ppm을 초과하더라도, 전단과 후단의 농도를 비교하여 산출한 '저감효율'이 {eff_limit}% 이상인 경우 최종 판정(result)을 '적합'으로 처리하세요.
   - 결과(value) 항목에는 "후단 107.7ppm (효율 92%)" 형태로 농도와 효율을 함께 기재하세요.
3. LDAR 누출 점검 (ldar): 2022년, 2023년, 2024년, 2025년 등 문서에 존재하는 '모든 연도'의 점검 실적을 단 한 해도 빼놓지 말고 전수조사하여 각각 추출하세요.

[🚨 냉각탑 및 열교환기 정밀 분석 필수 - 연도별 누락 절대 금지 🚨]
문서 내에 '냉각탑(Cooling Tower)' 또는 '열교환기(Heat Exchanger)'와 관련된 연 1회 점검 기록이 있는지 반드시 확인하고, 발견되면 `cooling` 객체의 `data` 배열에 담으세요.
- ❗️가장 중요: 2022년, 2023년, 2024년, 2025년 등 과거 연도의 데이터가 존재한다면 '절대 중간 연도를 빼먹지 말고' 모든 연도의 점검 기록을 개별 행(객체)으로 전부 추가해야 합니다. (AI 모델의 임의 요약 및 스킵을 엄격히 금지합니다)
- 측정 날짜(date)를 반드시 추출하여 `date` 속성에 기입하세요. (예: "2024-05-12")
- 냉각탑: 냉각수 TOC 분석 실시 여부 및 TOC 농도 50ppm 미만 유지 여부 (초과 시 부적합)
- 열교환기: 전·후단 냉각수 농도 편차 분석 실시 여부 및 편차 1ppm 미만 또는 10% 미만 유지 여부 (초과 시 부적합)
📌 [특수 계산 조건]: 만약 열교환기 항목에 측정 수치가 하나만 기재되어 있다면, 이는 '후단' 수치로 간주합니다. 이 경우 해당 연도의 '냉각탑 TOC 분석 결과값'을 찾아 열교환기의 '전단' 수치로 대입하여 두 수치의 편차를 직접 계산하세요.

[🚫 강력한 환각(Hallucination) 방지 지시사항 🚫]
서술형 의견(overall_opinion 등)을 작성할 때, 문서에서 실제로 추출된 연도, 시설명, 수치만을 100% 팩트 기반으로 서술하세요. 문서에 없는 과거 이력을 상상하거나 지어내지 마십시오. 문자열 안에 큰따옴표(")를 사용할 때는 반드시 백슬래시(\)로 이스케이프 처리하세요.

[★ 지식베이스 ★]
{retrieved_knowledge if retrieved_knowledge else "기본 환경 지식 활용"}

[★ 출력 형식 ★]
반드시 마크다운 없이 순수 JSON 객체로만 출력하세요. 속성명과 구조를 절대 바꾸지 마세요.
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"B"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "2025-05-26", "facility": "흡착에의한시설(7)", "value": "107.7ppm (효율 92%)", "limit": "{limit_text}", "result": "적합"}} ] }},
  "ldar": {{ "data": [ {{"year": "2025", "target_count": "10", "leak_count": "0", "leak_rate": "0%", "recheck_done": "이행완료", "result": "적합"}} ] }},
  "cooling": {{ "data": [
    {{"date": "2023-04-10", "facility": "냉각탑", "value": "2.6ppm", "limit": "50ppm 미만", "result": "적합"}},
    {{"date": "2024-05-12", "facility": "열교환기(CK-1)", "value": "편차 0.1ppm", "limit": "1ppm 미만", "result": "적합"}}
  ]}},
  "risk_matrix": [ {{"item": "시설관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검 강화", "expected_effect": "효율 안정화"}} ],
  "priority_actions": [ {{"priority": "1", "action": "냉각탑 TOC 정기검사", "deadline": "1개월 이내", "owner": "환경안전팀"}} ],
  "law_references": [ {{"law_name": "비산배출시설 관리기준", "article": "관련 조문", "summary": "냉각수 TOC 50ppm 미만 유지 의무", "checked_date": "2026-10-18"}} ],
  "followup_actions": [ {{"action": "열교환기 편차 점검", "owner": "관리자", "deadline": "분기 내", "status": "대기"}} ],
  "overall_opinion": "반드시 추출된 실제 데이터만을 기반으로 작성. 절대 가상의 과거 이력을 지어내지 말 것."
}}
"""
    try:
        # 💡 API 호출 시 JSON 문법 오류 원천 차단
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt] + measure_images,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        
        raw_text = response.text.strip()
        
        try:
            parsed_data = json.loads(raw_text, strict=False)
        except json.JSONDecodeError:
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            parsed_data = json.loads(raw_text, strict=False)
                
        return {"parsed": parsed_data, "raw": raw_text}
    
    except Exception as e:
        st.error(f"1단계 데이터 추출 중 API 오류 발생: {e}")
        return {"parsed": {}, "raw": f"에러 발생: {e}"}

def generate_advanced_air_advice(station_name: str, pm10_val: str, o3_val: str):
    time.sleep(3) 
    api_key = get_api_key()
    if not api_key: return "대기질 API 키 설정 오류."
            
    client = genai.Client(api_key=api_key)
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
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0.4)
        )
        return response.text.strip()
    except Exception as e:
        st.error(f"2단계 전문가 제언 중 API 오류 발생: {e}")
        return "AI 모델 통신 오류로 전문가 제언 생성을 일시 생략합니다."

# =====================================================================
# 🖥️ 3. Streamlit UI 및 메인 앱 실행
# =====================================================================
st.set_page_config(page_title="오프라인 AI 진단 보고서", page_icon="✨", layout="wide")

st.markdown("""
<style>
.stButton>button { width: 100%; font-weight: bold; }
.metric-box { padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; background-color: #f8f9fa; }
</style>
""", unsafe_allow_html=True)

st.title("✨ 비산배출시설 정밀 자가진단 (오프라인)")
st.info("환경부 비산배출시설 운영기록부(PDF, ZIP)를 업로드하면, AI가 법적 준수율을 분석하고 종합 보고서를 생성합니다.")

# 사이드바 설정 (관리자 모드 등)
with st.sidebar:
    st.header("⚙️ 진단 기본 설정")
    company_name = st.text_input("진단 사업장명", value="테스트 화학")
    addr = st.text_input("사업장 소재지 (시/군/구까지)", value="전북 전주")
    industry_type = st.selectbox("업종 분류", ["I업종", "II업종", "III업종", "IV업종", "기타"])
    permit_no = st.text_input("허가·신고 번호", value="제 2026-01 호")
    
    st.markdown("---")
    st.markdown("### 🔒 관리자 모드")
    admin_pw = st.text_input("관리자 암호를 입력하세요", type="password")
    
    if admin_pw == "1234":
        st.success("관리자 권한 활성화됨")
        st.markdown("#### ⚙️ 시스템 관리자 메뉴")
        st.caption("※ 환경부 매뉴얼 등 PDF를 ZIP으로 묶어서 올려주세요.")
        uploaded_kb = st.file_uploader("지식베이스용 ZIP 업로드", type=["zip"])
        if st.button("지식베이스 구축 (업데이트)", type="primary"):
            if uploaded_kb:
                with st.spinner("벡터 데이터베이스를 구축 중입니다... (1~2분 소요)"):
                    if build_vector_db(uploaded_kb):
                        st.success("지식베이스가 성공적으로 업데이트되었습니다!")
            else:
                st.warning("먼저 ZIP 파일을 업로드해 주세요.")
                
        st.markdown("#### 💾 지식베이스 백업")
        if os.path.exists(FAISS_DB_DIR):
            try:
                import shutil
                shutil.make_archive("faiss_backup", 'zip', FAISS_DB_DIR)
                with open("faiss_backup.zip", "rb") as f:
                    st.download_button("📥 완성된 DB 다운로드 (ZIP)", f, file_name="faiss_vector_db.zip", mime="application/zip")
            except Exception as e:
                st.error(f"백업 생성 실패: {e}")
        else:
            st.info("현재 구축된 지식베이스가 없습니다.")

# 메인 화면 (파일 업로드 및 진단 실행)
uploaded_logs = st.file_uploader("비산배출시설 운영기록부 업로드 (PDF 또는 ZIP)", type=["pdf", "zip"], accept_multiple_files=True)

if uploaded_logs:
    pdf_list = extract_pdfs_from_source(uploaded_logs)
    if pdf_list:
        st.success(f"✓ 총 {len(pdf_list)}개 진단 파일 등록 완료")
        
        if st.button("🚀 정밀 진단 시작", type="primary"):
            with st.spinner("AI 엔진 초기화 및 이미지 변환 중..."):
                images = convert_and_mask_images(pdf_list)
            
            if not images:
                st.error("처리 가능한 PDF 페이지가 없습니다.")
                st.stop()
                
            vector_db = load_vector_db()
            if vector_db is None:
                st.warning("⚠️ 구축된 지식베이스가 없어 기본 모델 지식으로만 진단을 수행합니다.")
            
            with st.spinner("AI가 방지시설, LDAR, 냉각탑 등 운영기록을 분석하고 있습니다... (약 1분 소요)"):
                diag_result = analyze_log_compliance(images, industry_type, vector_db)
            
            with st.spinner("대기환경 전문가의 실시간 대기질 연계 가이드를 생성 중입니다..."):
                # 실제 get_env_office 함수가 있다면 utils에서 임포트해야 하지만, 여기서는 샘플 데이터로 연동
                station_name = "성동면" 
                air_data = {"pm10Value": "11", "o3Value": "0.027"}
                expert_advice = generate_advanced_air_advice(station_name, air_data.get("pm10Value"), air_data.get("o3Value"))
            
            st.success("✅ AI 정밀 진단 및 보고서 생성이 성공적으로 완료되었습니다!")
            
            # PDF 생성 및 다운로드 버튼 제공
            user_info = {
                "name": company_name,
                "addr": addr,
                "industry": industry_type,
                "permit_no": permit_no
            }
            pdf_bytes = create_gov_report_pdf(diag_result, user_info, expert_advice, air_data, station_name)
            
            today_str = datetime.now().strftime("%Y%m%d")
            file_name = f"비산배출_정밀진단보고서_{company_name}_{today_str}.pdf"
            
            st.download_button(
                label="📥 최종 보고서 다운로드 (PDF)",
                data=pdf_bytes,
                file_name=file_name,
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
            
            with st.expander("🛠️ AI 엔진 Raw Data (디버깅용)"):
                st.json(diag_result)
    else:
        st.error("유효한 PDF 파일을 찾을 수 없습니다. (ZIP 내부 확인 필요)")
