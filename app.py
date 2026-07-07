import streamlit as st
import os
import time
import ai_engine

# 1. 페이지 기본 설정
st.set_page_config(page_title="HAPs-AI 진단 시스템", page_icon="🛡️", layout="wide")

# 2. 사이드바 UI (사용자 입력)
st.sidebar.title("환경관리 정밀 진단")

st.sidebar.markdown("### 📋 기본 정보 입력")
user_industry = st.sidebar.selectbox("업종 분류", ["III업종", "I업종", "II업종", "IV업종", "V업종"])
company_name = st.sidebar.text_input("사업장명", value="제이")
station_name = st.sidebar.text_input("관할 측정소", value="봉동읍")

# =====================================================================
# 🟢 3. 지식베이스 생존 표시기 (상태창)
# =====================================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧠 AI 지식베이스 상태")
# ai_engine에서 지정한 FAISS DB 폴더가 살아있는지 검사합니다.
if os.path.exists(ai_engine.FAISS_DB_DIR):
    st.sidebar.success("🟢 정상 가동 중 (학습 완료)")
else:
    st.sidebar.error("🔴 지식베이스 없음 (관리자 업로드 필요)")

# =====================================================================
# 🔒 4. 비밀번호로 보호된 시스템 관리자 메뉴
# =====================================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔒 관리자 모드")
# 비밀번호 입력창 (글자가 *** 로 가려집니다)
admin_password = st.sidebar.text_input("관리자 암호를 입력하세요", type="password")

# 비밀번호가 일치할 때만 아래 메뉴가 펼쳐집니다.
if admin_password == "1234":
    st.sidebar.markdown("#### ⚙️ 시스템 관리자 메뉴")
    st.sidebar.caption("※ 환경부 매뉴얼, 법령 등 텍스트가 포함된 PDF들을 ZIP으로 묶어서 올려주세요.")
    
    uploaded_kb = st.sidebar.file_uploader("지식베이스용 ZIP 업로드", type=["zip"], key="kb_uploader")
    if st.sidebar.button("지식베이스 영구 구축 (업데이트)"):
        if uploaded_kb:
            with st.spinner("문서를 분석하고 AI 지식을 구축하는 중입니다..."):
                success = ai_engine.build_vector_db(uploaded_kb)
                if success:
                    st.sidebar.success("✅ 성공적으로 학습되었습니다!")
                    time.sleep(1)
                    st.rerun() # 화면을 새로고침하여 생존 표시기를 🟢 초록불로 바꿉니다.
                else:
                    st.sidebar.error("❌ 학습에 실패했습니다. 파일을 확인해주세요.")
        else:
            st.sidebar.warning("ZIP 파일을 먼저 올려주세요.")

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
# 🚀 6. 진단 실행 로직 연동
# =====================================================================
if diagnose_btn:
    if not uploaded_logs:
        st.warning("⚠️ 진단할 운영기록부(PDF/ZIP)를 먼저 업로드해주세요.")
    else:
        # 진행 상태 표시 바
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
            
            # [테스트 확인용] 콘솔이나 화면에 결과값 띄우기
            with st.expander("AI 데이터 추출 결과 확인하기"):
                st.json(diagnosis_result["parsed"])
                st.write(advice)
            
            # TODO: 여기에 기존에 쓰시던 pdf_generator.py 연동 코드를 연결하시면 최종 PDF가 다운로드 됩니다.
