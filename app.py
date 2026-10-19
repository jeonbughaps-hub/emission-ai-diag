import streamlit as st
import os
import time
import shutil
from datetime import datetime
import json
import re
import fitz
import gc
from PIL import Image
import io
import zipfile
from google import genai
from google.genai import types

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS

import ai_engine
import pdf_generator

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

FAISS_DB_DIR = "faiss_vector_db"

# =====================================================================
# 1. 페이지 기본 설정 및 디자인
# =====================================================================
st.set_page_config(
    page_title="HAPs-AI | 환경관리 정밀진단",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');

:root {
    --navy: #102A43;
    --navy-2: #163B5C;
    --teal: #0F9D91;
    --teal-dark: #087F75;
    --ink: #243B53;
    --muted: #627D98;
    --line: #D9E2EC;
    --surface: #FFFFFF;
    --canvas: #F4F7FB;
    --soft-teal: #E7F7F4;
}
html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
.stApp { background: var(--canvas); color: var(--ink); }
[data-testid="stHeader"] { background: rgba(244,247,251,.92); }
.block-container { padding-top: 1.35rem; padding-bottom: 3rem; max-width: 1500px; }

/* 사이드바 스타일링 */
[data-testid="stSidebar"] { background: #102A43; border-right: 1px solid #254765; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] *,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stCaption { color: #D8E7F2 !important; }
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] input { background: #FFFFFF !important; color: #102A43 !important; border-radius: 9px !important; font-weight: 600; }
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] .stDownloadButton > button { background: #0F9D91 !important; color: #FFFFFF !important; border: 1px solid #14B8A6 !important; width: 100%; }
[data-testid="stSidebar"] .stButton > button:hover { background: #087F75 !important; }

/* 메인 컨텐츠 스타일링 */
h1, h2, h3 { color: var(--navy); letter-spacing: -.035em; font-weight: 800 !important; }
[data-testid="stMetric"] { background: white; border: 1px solid var(--line); border-radius: 15px; padding: 16px 18px; box-shadow: 0 4px 14px rgba(16,42,67,.035); }
[data-testid="stMetricLabel"] p { color: var(--muted) !important; font-weight: 600; }
[data-testid="stMetricValue"] { color: var(--navy); font-weight: 800; }
.stButton > button[kind="primary"] { background: var(--teal); color: white; border-radius: 10px; min-height: 2.8rem; font-weight: 700; }
.stButton > button[kind="primary"]:hover { background: var(--teal-dark); box-shadow: 0 5px 14px rgba(15,157,145,.2); }

/* 커스텀 컴포넌트 */
.hero { background: linear-gradient(115deg, #102A43 0%, #163B5C 65%, #176C75 100%); color: white; padding: 28px 30px; border-radius: 20px; margin: 0 0 22px 0; position: relative; overflow: hidden; }
.hero h1 { color: white !important; font-size: clamp(1.55rem, 2.4vw, 2.25rem); margin: 0 0 8px 0; }
.hero p { color: #D8E7F2; margin: 0; }
.hero-tag { display: inline-block; background: rgba(15,157,145,.18); border: 1px solid rgba(130,235,221,.4); color: #BDF7EC; padding: 5px 10px; border-radius: 999px; font-size: .75rem; font-weight: 700; margin-bottom: 13px; }
.section-heading { font-size: 1.12rem; font-weight: 800; color: var(--navy); margin: 0 0 4px 0; }
.section-sub { color: var(--muted); font-size: .88rem; margin: 0 0 16px 0; }
.panel { background: white; border: 1px solid var(--line); border-radius: 16px; padding: 20px 22px; margin-bottom: 12px; }
.panel-kicker { color: var(--teal-dark); font-size: .75rem; font-weight: 800; letter-spacing: .08em; }
.panel-title { color: var(--navy); font-size: 1.08rem; font-weight: 800; margin: 4px 0 7px 0; }
.panel-copy { color: var(--muted); font-size: .88rem; }
.step-row { display: flex; gap: 8px; margin: 8px 0 20px 0; }
.step { flex: 1; padding: 10px 12px; border-radius: 10px; text-align: center; border: 1px solid var(--line); background: white; color: var(--muted); font-size: .81rem; font-weight: 700; }
.step.active { background: var(--soft-teal); border-color: #83D6CB; color: var(--teal-dark); }
.step-number { display: inline-flex; width: 22px; height: 22px; border-radius: 50%; background: #EAF0F6; color: var(--navy); align-items: center; justify-content: center; margin-right: 5px; font-size: .75rem; }
.step.active .step-number { background: var(--teal); color: white; }
.status-pill { display: inline-block; border-radius: 999px; padding: 5px 12px; background: #E7F7F4; color: #087F75; font-size: .78rem; font-weight: 800; margin-bottom: 8px; }
</style>
""", unsafe_allow_html=True)

# =====================================================================
# 3. 사이드바 UI (사업장 입력 & 지능형 측정소 자동 매핑)
# =====================================================================
def get_mapped_station(region_val: str, district_val: str) -> str:
    district_station_map = {
        "논산": "성동면", "청주": "오창읍", "천안": "백석동", "아산": "배방읍",
        "서산": "대산읍", "당진": "송산면", "공주": "봉황동", "완주": "봉동읍",
        "전주": "삼천동", "군산": "소룡동", "익산": "팔봉동", "여수": "삼일동",
        "순천": "장천동", "광양": "태인동", "대덕": "문평동", "유성": "구성동"
    }
    combined = f"{region_val} {district_val}".strip()
    for key, station in district_station_map.items():
        if key in district_val or key in combined: return station
    
    region_fallback = {"충청": "오창읍", "대전": "문평동", "세종": "아름동", "전라": "봉동읍", "광주": "평동"}
    if district_val.strip(): return f"{district_val.strip()}"
    return region_fallback.get(region_val, "봉동읍")

with st.sidebar:
    st.markdown("""<div style="padding:10px 2px 14px;"><div style="font-size:2rem; margin-bottom:4px;">🛡️</div><div style="font-size:1.15rem; font-weight:800; color:#FFFFFF;">HAPs-AI 진단 시스템</div><div style="font-size:.76rem; color:#AFC5D7; margin-top:4px;">비산배출시설 정밀 자가진단 · Pilot</div></div>""", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### 📋 기본 정보 입력")
    user_industry = st.selectbox("업종 분류", ["III업종", "I업종", "II업종", "IV업종", "V업종"])
    company_name = st.text_input("사업장명", value="로테")
    permit_no = st.text_input("허가·신고 번호", value="")

    col_region, col_district = st.columns(2)
    with col_region: region = st.selectbox("지역", ["충청", "대전", "세종", "전라", "광주"], index=3)
    with col_district: district = st.text_input("구 단위", value="여수")

    company_location = f"{region} {district}".strip()
    default_station = get_mapped_station(region, district)
    station_name = st.text_input("관할 측정소", value=default_station, key=f"st_{company_location}")
    st.caption("소재지 기준으로 관할 대기측정소를 자동 매핑합니다.")

    st.markdown("---")
    st.markdown("### 🧠 AI 지식베이스 상태")
    if os.path.exists("index.faiss") and os.path.exists("index.pkl"):
        if not os.path.exists(FAISS_DB_DIR): os.makedirs(FAISS_DB_DIR)
        shutil.move("index.faiss", os.path.join(FAISS_DB_DIR, "index.faiss"))
        shutil.move("index.pkl", os.path.join(FAISS_DB_DIR, "index.pkl"))

    if os.path.exists(FAISS_DB_DIR):
        st.success("🟢 정상 가동 중 (영구 구축됨)")
    else:
        st.error("🔴 지식베이스 없음 (관리자 업로드 필요)")

    st.markdown("---")
    st.markdown("### 🔒 관리자 모드")
    admin_password = st.text_input("관리자 암호를 입력하세요", type="password")

    if admin_password == "1234":
        uploaded_kb = st.file_uploader("지식베이스용 ZIP 업로드", type=["zip"])
        if st.button("지식베이스 구축 (업데이트)", use_container_width=True):
            if uploaded_kb and ai_engine.build_vector_db(uploaded_kb):
                st.success("✅ 성공적으로 학습되었습니다!")
                time.sleep(1)
                st.rerun()
            else: st.error("❌ 학습 실패 또는 파일 누락.")

# =====================================================================
# 4. 메인 화면 UI
# =====================================================================
st.markdown("""<div class="hero"><div class="hero-tag">ENVIRONMENTAL COMPLIANCE · AI PRECISION DIAGNOSIS</div><h1>🛡️ 비산배출시설 환경관리 정밀 진단 시스템</h1><p>멀티모달 AI 및 법령 지식베이스(RAG)를 활용하여 운영기록부 법적 준수 여부를 전수 점검하고 맞춤형 개선 보고서를 자동 발행합니다.</p></div>""", unsafe_allow_html=True)

info1, info2, info3, info4 = st.columns([1.25, 1.25, 1.15, 1.35])
with info1: st.markdown(f"""<div class="panel"><div class="panel-kicker">FACILITY</div><div class="panel-title">🏭 {company_name}</div><div class="panel-copy">진단 대상 사업장</div></div>""", unsafe_allow_html=True)
with info2: st.markdown(f"""<div class="panel"><div class="panel-kicker">INDUSTRY</div><div class="panel-title">📑 {user_industry}</div><div class="panel-copy">비산배출 업종 분류</div></div>""", unsafe_allow_html=True)
with info3: st.markdown(f"""<div class="panel"><div class="panel-kicker">LOCATION</div><div class="panel-title">📍 {company_location}</div><div class="panel-copy">사업장 소재지</div></div>""", unsafe_allow_html=True)
with info4: st.markdown(f"""<div class="panel"><div class="panel-kicker">STATION</div><div class="panel-title">🌐 {station_name}</div><div class="panel-copy">공공데이터 관할 측정소</div></div>""", unsafe_allow_html=True)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
st.markdown('<div class="section-heading">진단 작업 공간</div><div class="section-sub">점검 대상 운영기록부를 등록한 뒤 AI 정밀 진단을 실행하세요.</div>', unsafe_allow_html=True)
st.markdown("""<div class="step-row"><div class="step active"><span class="step-number">1</span>운영기록부 등록</div><div class="step"><span class="step-number">2</span>AI 멀티모달 분석</div><div class="step"><span class="step-number">3</span>법령 RAG 교차검증</div><div class="step"><span class="step-number">4</span>공식 PDF 보고서 발급</div></div>""", unsafe_allow_html=True)

col1, col2 = st.columns([1.55, 1], gap="large")

with col1:
    st.markdown("""<div class="panel"><div class="panel-kicker">01 / DOCUMENT INTAKE</div><div class="panel-title">📝 운영기록부 업로드 (진단 대상)</div><div class="panel-copy">PDF 파일 또는 다수 PDF가 포함된 ZIP 압축파일을 올려주세요.</div></div>""", unsafe_allow_html=True)
    uploaded_logs = st.file_uploader("문서 업로드", type=["pdf", "zip"], accept_multiple_files=True, label_visibility="collapsed")
    if uploaded_logs:
        st.markdown(f'<span class="status-pill">✓ 총 {len(uploaded_logs)}개 진단 파일 등록 완료</span>', unsafe_allow_html=True)
    diagnose_btn = st.button("🚀 정밀 진단 시작", type="primary", use_container_width=True)

with col2:
    st.markdown(f"""<div class="panel"><div class="panel-kicker">02 / LOCAL AIR QUALITY</div><div class="panel-title">📊 지역 실시간 대기질 ({station_name})</div><div class="panel-copy">관할 측정소의 대기오염물질 농도를 기반으로 연계 분석합니다.</div></div>""", unsafe_allow_html=True)
    st.metric(label="오존 (O3)", value="0.027 ppm", delta="기준: 0.09", delta_color="normal")
    st.metric(label="미세먼지 (PM10)", value="11 µg/m³", delta="기준: 80", delta_color="normal")

# =====================================================================
# 5. 진단 실행 로직 연동 및 PDF 다운로드
# =====================================================================
if diagnose_btn:
    if not uploaded_logs:
        st.warning("⚠️ 진단할 운영기록부(PDF/ZIP)를 먼저 업로드해주세요.")
    else:
        my_bar = st.progress(0.1, text="PDF 문서 정밀 스캔 중...")
        pdf_list = ai_engine.extract_pdfs_from_source(uploaded_logs)
        measure_images = ai_engine.convert_and_mask_images(pdf_list)
        
        my_bar.progress(0.4, text="AI 전수조사 데이터 정밀 추출 중...")
        vector_db = ai_engine.load_vector_db()
        diagnosis_result = ai_engine.analyze_log_compliance(measure_images, user_industry, vector_db)

        my_bar.progress(0.8, text="전문가 제언 작성 중...")
        advice = ai_engine.generate_advanced_air_advice(station_name, "11", "0.027")

        my_bar.progress(1.0, text="완료!")
        time.sleep(0.5)
        my_bar.empty()

        st.success("✅ AI 정밀 진단 및 보고서 생성이 성공적으로 완료되었습니다!")

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="section-heading">📊 AI 정밀 진단 결과 브리핑</div><div class="section-sub">추출된 핵심 지표와 전문가 제언을 확인하고 공식 PDF 보고서를 다운로드하세요.</div>', unsafe_allow_html=True)
        
        parsed = diagnosis_result.get("parsed", {})
        scores = parsed.get("scores", {})
        overall = scores.get("overall_score", {})
        
        result_col1, result_col2, result_col3 = st.columns(3)
        with result_col1: st.metric("종합 진단 점수", f'{overall.get("score", "-")}점')
        with result_col2: st.metric("종합 적합성 등급", f'{overall.get("grade", "-")} 등급')
        with result_col3: st.metric("진단 대상 사업장", company_name or "-")

        tab1, tab2, tab3 = st.tabs(["📌 AI 종합 의견 및 로드맵", "🌱 대기환경 전문가 제언", "🔎 AI 데이터 추출 원본 (JSON)"])
        with tab1:
            st.info(parsed.get("overall_opinion", "종합 의견 데이터가 없습니다."))
            roadmap_data = parsed.get("improvement_roadmap", [])
            if isinstance(roadmap_data, list) and len(roadmap_data) > 0:
                st.dataframe(roadmap_data, use_container_width=True, hide_index=True)
        with tab2: st.write(advice)
        with tab3: st.json(parsed)

        with st.spinner("최종 PDF 보고서를 디자인하고 있습니다..."):
            try:
                user_info_dict = {"name": company_name, "addr": company_location, "industry": user_industry, "permit_no": permit_no}
                air_data_dict = {"pm10Value": "11", "o3Value": "0.027"}

                pdf_bytes = pdf_generator.create_gov_report_pdf(
                    ai_data=diagnosis_result,
                    user_info=user_info_dict,
                    air_advice=advice,
                    air_data=air_data_dict,
                    station_name=station_name
                )

                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                st.download_button(
                    label="📥 진단 보고서 다운로드 (PDF)",
                    data=pdf_bytes,
                    file_name=f"비산배출_정밀진단보고서_{company_name}_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"PDF 생성 중 오류가 발생했습니다: {e}")

st.markdown("""<div class="footer-note">HAPs-AI 비산배출시설 환경관리 정밀 진단 시스템 · Pilot Edition<br/>본 시스템은 대기환경보전법 및 환경부 비산배출시설 관리 매뉴얼(RAG)을 기반으로 자가진단 결과를 제공합니다.</div>""", unsafe_allow_html=True)
