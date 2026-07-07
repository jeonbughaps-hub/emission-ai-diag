import streamlit as st
import os
import time
import shutil
from datetime import datetime
import ai_engine
import pdf_generator 

# =====================================================================
# 1. 페이지 기본 설정
# =====================================================================
st.set_page_config(page_title="HAPs-AI 진단 시스템", page_icon="🛡️", layout="wide")

# =====================================================================
# 2. 사이드바 UI (사용자 입력 & 동적 매핑)
# =====================================================================
st.sidebar.title("환경관리 정밀 진단")

st.sidebar.markdown("### 📋 기본 정보 입력")
user_industry = st.sidebar.selectbox("업종 분류", ["III업종", "I업종", "II업종", "IV업종", "V업종"])
company_name = st.sidebar.text_input("사업장명", value="제이")

# 공공데이터 연동을 위한 소재지 분할 입력
col_region, col_district = st.sidebar.columns(2)
with col_region:
    region = st.selectbox("지역", ["충청", "대전", "세종", "전라", "광주"], index=3)
with col_district:
    district = st.text_input("구 단위", value="완주")

company_location = f"{region} {district}".strip()

# 💡 지역별 관할 측정소 자동 매핑 사전 
station_mapping = {
    "전라 완주": "봉동읍",
    "전라 전주": "삼천동",
    "충청 청주": "오창읍",
    "충청 천안": "백석동",
    "대전 대덕": "문평동",
    "세종 세종": "아름동",
    "광주 광산": "평동"
}

default_station = station_mapping.get(company_location, "봉동읍")
station_name = st.sidebar.text_input("관할 측정소", value=default_station)

# =====================================================================
# 🟢 3. 지식베이스 생존 표시기 (자동 복구 마법 포함)
# =====================================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧠 AI 지식베이스 상태")

if os.path.exists("index.faiss") and os.path.exists("index.pkl"):
    if not os.path.exists(ai_engine.FAISS_DB_DIR):
        os.makedirs(ai_engine.FAISS_DB_DIR)
    shutil.move("index.faiss", os.path.join(ai_engine.FAISS_DB_DIR, "index.faiss"))
    shutil.move("index.pkl", os.path.join(ai_engine.FAISS_DB_DIR, "index.pkl"))

if os.path.exists(ai_engine.FAISS_DB_DIR):
    st.sidebar.success("🟢 정상 가동 중 (영구 구축됨)")
else:
    st.sidebar.error("🔴 지식베이스 없음 (관리자 업로드 필요)")

# =====================================================================
# 🔒 4. 비밀번호로 보호된 시스템 관리자 메뉴
# =====================================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔒 관리자 모드")
admin_password = st.sidebar.text_input("관리자 암호를 입력하세요", type="password")

if admin_password == "1234":
    st.sidebar.markdown("#### ⚙️ 시스템 관리자 메뉴")
    st.sidebar.caption("※ 환경부 매뉴얼 등 PDF를 ZIP으로 묶어서 올려주세요.")
    
    uploaded_kb = st.sidebar.file_uploader("지식베이스용 ZIP 업로드", type=["zip"], key="kb_uploader")
    if st.sidebar.button("지식베이스 구축 (업데이트)"):
        if uploaded_kb:
            with st.spinner("문서를 분석하고 AI 지식을 구축하는 중입니다..."):
                success = ai_engine.build_vector_db(uploaded_kb)
                if success:
                    st.sidebar.success("✅ 성공적으로 학습되었습니다!")
                    time.sleep(1)
                    st.rerun() 
                else:
                    st.sidebar.error("❌ 학습에 실패했습니다.")
        else:
            st.sidebar.warning("ZIP 파일을 먼저 올려주세요.")
            
    if os.path.exists(ai_engine.FAISS_DB_DIR):
        st.sidebar.markdown("---")
        st.sidebar.markdown("#### 💾 지식베이스 백업")
        shutil.make_archive("faiss_vector_db", 'zip', ai_engine.FAISS_DB_DIR)
        with open("faiss_vector_db.zip", "rb") as f:
            st.sidebar.download_button(
                label="📥 완성된 DB 다운로드 (ZIP)",
                data=f,
                file_name="faiss_vector_db.zip",
                mime="application/zip"
            )

# =====================================================================
# 🖥️ 5. 메인 화면 UI
# =====================================================================
st.title("🛡️ 비산배출시설 환경관리 정밀 진단 시스템")
st.markdown("---")

col1, col2 = st.columns([6, 4])

with col1:
    st.markdown("### 📝 운영기록부 업로드 (진단 대상)")
    st.caption("PDF 파일 또는 다수 PDF가 포함된 ZIP 압축파일을 올려주세요")
    uploaded_logs = st.file_uploader("", type=["pdf", "zip"], accept_multiple_files=True)
    
    diagnose_btn = st.button("🚀 정밀 진단 시작")

with col2:
    st.markdown("### 📊 지역 실시간 대기질")
    st.metric(label="오존 (O3)", value="0.027 ppm", delta="기준: 0.09", delta_color="normal")
    st.metric(label="미세먼지 (PM10)", value="11 µg/m³", delta="기준: 80", delta_color="normal")

# =====================================================================
# 🚀 6. 진단 실행 로직 연동 및 PDF 다운로드
# =====================================================================
if diagnose_btn:
    if not uploaded_logs:
        st.warning("⚠️ 진단할 운영기록부(PDF/ZIP)를 먼저 업로드해주세요.")
    else:
        progress_text = "PDF 문서 정밀 스캔 중..."
        my_bar = st.progress(0.1, text=progress_text)
        
        pdf_list = ai_engine.extract_pdfs_from_source(uploaded_logs)
        measure_images = ai_engine.convert_and_mask_images(pdf_list)
        my_bar.progress(0.4, text="AI 지식베이스 연동 및 데이터 정밀 추출 중...")
        
        if not measure_images:
            st.error("이미지로 변환할 수 있는 유효한 PDF 페이지가 없습니다.")
            my_bar.empty()
        else:
            vector_db = ai_engine.load_vector_db()
            diagnosis_result = ai_engine.analyze_log_compliance(measure_images, user_industry, vector_db)
            
            my_bar.progress(0.8, text="전문가 제언 작성 중...")
            advice = ai_engine.generate_advanced_air_advice(station_name, "11", "0.027")
            
            my_bar.progress(1.0, text="완료!")
            time.sleep(0.5)
            my_bar.empty()

            st.success("✅ AI 정밀 진단 및 보고서 생성이 성공적으로 완료되었습니다!")
            
            with st.expander("AI 데이터 추출 결과 확인하기"):
                st.json(diagnosis_result["parsed"])
                st.write(advice)
            
            # ==========================================
            # 📄 PDF 보고서 생성 및 다운로드 버튼 처리 (🚨 완벽 수정됨)
            # ==========================================
            with st.spinner("최종 PDF 보고서를 디자인하고 있습니다..."):
                try:
                    # pdf_generator 규격에 맞게 데이터 패키징
                    user_info_dict = {
                        "name": company_name,
                        "addr": company_location,
                        "industry": user_industry,
                        "permit_no": "-"
                    }
                    
                    air_data_dict = {
                        "pm10Value": "11",
                        "o3Value": "0.027"
                    }
                    
                    # 파일 저장 없이 서버 메모리에서 즉시 바이트(bytes) 데이터로 뽑아냅니다.
                    pdf_bytes = pdf_generator.create_gov_report_pdf(
                        ai_data=diagnosis_result,
                        user_info=user_info_dict,
                        air_advice=advice,
                        air_data=air_data_dict,
                        station_name=station_name
                    )
                    
                    st.download_button(
                        label="📥 진단 보고서 다운로드 (PDF)",
                        data=pdf_bytes,
                        file_name=f"비산배출_정밀진단보고서_{company_name}_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf"
                    )
                except Exception as e:
                    st.error(f"PDF 생성 중 오류가 발생했습니다: {e}")
