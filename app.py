import os
import streamlit as st
from datetime import datetime

# 개발하신 외부 모듈 임포트
import ai_engine
from pdf_generator import create_gov_report_pdf
from utils import get_auto_station_and_coord, get_air_quality

# =====================================================================
# 1. 페이지 및 기본 환경 설정
# =====================================================================
st.set_page_config(page_title="HAPs-AI 진단 시스템", page_icon="🛡️", layout="wide")

# 세션 초기값 세팅
if "target_station" not in st.session_state:
    st.session_state.target_station = "내포"

# 공공데이터 API 키 및 Gemini API 키 (Streamlit Secrets 또는 환경 변수 활용 권장)
AIR_API_KEY = os.environ.get("AIR_API_KEY", "여기에_에어코리아_API키_입력_또는_os.environ유지")

# =====================================================================
# 2. 좌측 사이드바 (사용자 정보 & 관리자 메뉴)
# =====================================================================
with st.sidebar:
    st.markdown("### 🏢 사업장 기본 정보")
    user_addr = st.text_input("사업장 주소", value="광주광역시 광산구")
    user_industry = st.selectbox("업종 분류", ["I업종", "II업종", "III업종", "IV업종", "V업종"], index=2)
    user_name = st.text_input("사업장명", value="성원")
    
    # 주소 기반 관할 측정소 자동 매핑 (utils.py)
    station_name, coords = get_auto_station_and_coord(user_addr)
    st.session_state.target_station = station_name
    st.info(f"📍 관할 측정소: {station_name}")
    
    # 🚨 [새로 추가된 영역] 시스템 관리자 전용 지식베이스 구축 메뉴
    st.markdown("---")
    st.markdown("### ⚙️ 시스템 관리자 메뉴")
    st.caption("※ 환경부 매뉴얼, 법령 등 텍스트가 포함된 PDF들을 ZIP으로 묶어서 올려주세요.")
    kb_zip = st.file_uploader("지식베이스용 ZIP 업로드", type=["zip"], key="kb_upload")
    
    if kb_zip and st.button("🧠 지식베이스 영구 구축"):
        with st.spinner("서버 하드디스크에 지식베이스를 학습 및 저장 중입니다..."):
            success = ai_engine.build_vector_db(kb_zip)
            if success:
                st.success("✅ 지식베이스 구축 완료! 이제 팩트 기반 진단이 적용됩니다.")
            else:
                st.error("❌ 지식베이스 구축에 실패했습니다.")

# =====================================================================
# 3. 메인 화면 (대시보드 및 AI 진단 실행)
# =====================================================================
st.markdown("## 🛡️ 비산배출시설 환경관리 정밀 진단 시스템")
st.markdown("<br>", unsafe_allow_html=True)

col1, col2 = st.columns([1.5, 1])

# --- 우측: 실시간 대기질 대시보드 ---
with col2:
    st.markdown("### 📊 지역 실시간 대기질")
    air_data = get_air_quality(station_name, AIR_API_KEY)
    pm10_val = air_data.get("pm10Value", "-")
    o3_val = air_data.get("o3Value", "-")
    
    st.metric("오존 (O3)", f"{o3_val} ppm", delta="기준: 0.09", delta_color="off")
    st.metric("미세먼지 (PM10)", f"{pm10_val} ㎍/m³", delta="기준: 80", delta_color="off")

# --- 좌측: 파일 업로드 및 진단 로직 ---
with col1:
    st.markdown("### 📝 운영기록부 업로드 (진단 대상)")
    main_files = st.file_uploader(
        "PDF 파일 또는 다수 PDF가 포함된 ZIP 압축파일을 올려주세요", 
        type=["pdf", "zip"], 
        accept_multiple_files=True, 
        key="main"
    )
    
    if st.button("🚀 정밀 진단 시작"):
        if not main_files:
            st.error("분석할 운영기록부 파일을 업로드해주세요.")
        else:
            try:
                # 1. 파일 추출 (일반 PDF 및 ZIP 압축 해제)
                with st.spinner("1/5. 업로드된 문서 파일을 추출 중입니다..."):
                    pdf_list = ai_engine.extract_pdfs_from_source(main_files)
                    if not pdf_list:
                        st.error("유효한 PDF 문서를 찾을 수 없습니다.")
                        st.stop()
                
                # 2. 이미지 변환 (메모리 최적화 적용)
                # (progress 바는 ai_engine 내부에 구현되어 있음)
                converted_images = ai_engine.convert_and_mask_images(pdf_list)
                
                # 3. 지식베이스(RAG DB) 몰래 불러오기
                with st.spinner("3/5. 저장된 환경 법규 지식베이스를 연동 중입니다..."):
                    loaded_vector_db = ai_engine.load_vector_db()
                
                # 4. AI 정밀 진단 (RAG DB 주입)
                with st.spinner("4/5. AI 엔진이 데이터를 정밀 분석 중입니다..."):
                    ai_data = ai_engine.analyze_log_compliance(converted_images, user_industry, loaded_vector_db)
                    
                # 5. 전문가 제언 및 PDF 렌더링
                with st.spinner("5/5. 대기환경 전문가 제언 작성 및 보고서 생성 중..."):
                    air_advice = ai_engine.generate_advanced_air_advice(station_name, str(pm10_val), str(o3_val))
                    
                    user_info = {
                        "name": user_name,
                        "addr": user_addr,
                        "industry": user_industry,
                        "permit_no": "-"
                    }
                    pdf_bytes = create_gov_report_pdf(ai_data, user_info, air_advice, air_data, station_name)
                
                # 결과 출력 및 다운로드
                st.success("✅ AI 정밀 진단 및 보고서 생성이 성공적으로 완료되었습니다!")
                st.download_button(
                    label="📥 진단 보고서 다운로드 (PDF)",
                    data=pdf_bytes,
                    file_name=f"비산배출_정밀진단보고서_{user_name}_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"분석 중 치명적인 오류가 발생했습니다: {e}")
