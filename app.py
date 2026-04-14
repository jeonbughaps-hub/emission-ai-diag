import streamlit as st
import os
from datetime import datetime

# 관련 모듈 임포트
from utils import (
    get_auto_station_and_coord, get_air_quality, get_env_office, 
    generate_rich_advice, get_limit_ppm
)
from ai_engine import (
    extract_pdfs_from_source, build_vector_db, 
    convert_and_mask_images, analyze_log_compliance
)
from pdf_generator import create_gov_report_pdf

# 1. API 키 설정 (Secrets 활용)
try:
    AIRKOREA_API_KEY = st.secrets["AIRKOREA_API_KEY"]
    os.environ["GOOGLE_API_KEY"] = st.secrets["GOOGLE_API_KEY"]
except Exception:
    st.error("Secrets 설정에서 API 키를 확인해주세요.")
    st.stop()

st.set_page_config(page_title="HAPs-AI 진단 시스템", layout="wide")

# 세션 상태 초기화
if "target_station" not in st.session_state:
    st.session_state.target_station = "내포"

st.title("🛡️ 비산배출시설 환경관리 정밀 진단 시스템")

with st.sidebar:
    st.header("🏢 사업장 기본 정보")
    user_addr = st.text_input("사업장 주소", "충남 홍성군 구항면")
    
    # 주소 입력 시 측정소 자동 갱신
    new_station, coords = get_auto_station_and_coord(user_addr)
    st.session_state.target_station = new_station
    
    user_industry = st.selectbox("업종 분류", ["I업종", "II업종", "III업종"], index=2)
    user_name = st.text_input("사업장명", "nox")
    
    st.info(f"📍 관할 측정소: {st.session_state.target_station}")

# 2. 실시간 공공데이터 연동
air_data = get_air_quality(st.session_state.target_station, AIRKOREA_API_KEY)
advice_text = generate_rich_advice(air_data, st.session_state.target_station)

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📝 운영기록부 업로드 (진단 대상)")
    main_files = st.file_uploader("PDF 파일을 올려주세요", accept_multiple_files=True, key="main")
    
    if st.button("🚀 정밀 진단 시작", type="primary"):
        if not main_files:
            st.warning("분석할 운영기록부 파일을 업로드해주세요.")
        else:
            with st.spinner("AI가 지식베이스를 바탕으로 정밀 분석 중입니다..."):
                # 이미지 변환 및 분석
                pdf_list = extract_pdfs_from_source(main_files)
                images = convert_and_mask_images(pdf_list)
                
                # 서버 지식베이스(VDB) 빌드
                vdb = build_vector_db()
                
                # 분석 수행
                result = analyze_log_compliance(images, user_industry, vdb)
                
                if result["parsed"]:
                    st.success("✅ 분석 완료!")
                    
                    # PDF 생성
                    user_info = {
                        "name": user_name, "addr": user_addr, 
                        "industry": user_industry, "office": get_env_office(user_addr)
                    }
                    pdf_bytes = create_gov_report_pdf(result["parsed"], user_info, advice_text, air_data, st.session_state.target_station)
                    
                    st.download_button(
                        "📄 정밀 진단 보고서 다운로드",
                        data=pdf_bytes,
                        file_name=f"비산배출_정밀진단보고서_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.error("분석 중 오류가 발생했습니다.")

with col2:
    st.subheader("📊 지역 실시간 대기질")
    if air_data:
        st.metric("오존(O3)", f"{air_data.get('o3Value', '-')} ppm")
        st.metric("미세먼지(PM10)", f"{air_data.get('pm10Value', '-')} ug/m³")
    else:
        st.error("데이터를 불러올 수 없습니다. API 키를 확인하세요.")
