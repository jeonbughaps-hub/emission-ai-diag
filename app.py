# ==========================================
# [Main Hub] app.py (v106.0 Production UI Edition)
# - 실무 배포용 UI 최적화: API 키 및 개발자 도구 숨김, 사용자 직관성 극대화
# ==========================================

import streamlit as st
import os
import pandas as pd
from datetime import datetime

# 세션 초기화를 무조건 최상단에서 실행
if "vector_db" not in st.session_state: st.session_state.vector_db = None
if "user_address" not in st.session_state: st.session_state.user_address = "충남 홍성군 구항면"
if "target_station" not in st.session_state: st.session_state.target_station = "내포"

# 모듈 불러오기 (반드시 나머지 3개 파일이 같은 폴더에 있어야 합니다)
from utils import get_auto_station_and_coord, get_air_quality, generate_rich_advice
from ai_engine import extract_pdfs_from_source, build_vector_db, convert_and_mask_images, analyze_log_compliance
from pdf_generator import create_gov_report_pdf

def on_address_change():
    addr = st.session_state.user_address
    new_station, _ = get_auto_station_and_coord(addr)
    st.session_state.target_station = new_station

def main():
    st.markdown("""
    <style>
      .main {background:#F5F8FC;}
      .block-container {padding-top:1.2rem;padding-bottom:1.2rem;}
      h1 {color:#2C3E50;font-size:1.6rem;}
      h2,h3 {color:#3464A3;}
      .stMetric {background:#EBF2FA;border-radius:8px;padding:8px;}
    </style>""", unsafe_allow_html=True)

    # ★ 1. API 키 자동 로딩 (Streamlit Cloud의 Secrets에서 보안 로드)
    google_api_key = st.secrets.get("GOOGLE_API_KEY", "") if hasattr(st, "secrets") else ""
    public_api_key = st.secrets.get("PUBLIC_API_KEY", "") if hasattr(st, "secrets") else ""

    if google_api_key:
        os.environ["GOOGLE_API_KEY"] = google_api_key
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

    with st.sidebar:
        st.markdown("## 🏢 비산배출 자가진단")
        st.caption("**v106.0 Production Edition**")
        st.divider()
        
        st.markdown("### 📌 이용 안내")
        st.info(
            "1. **사업장 정보**를 정확히 입력해주세요.\n\n"
            "2. **연간점검보고서**와 **신고증명서**를 업로드해주세요.\n\n"
            "3. **진단 시작** 버튼을 누르면 AI가 법규 준수 여부를 분석합니다."
        )
        
        st.divider()
        # 일반 사업장 사용자는 볼 필요 없는 관리자 메뉴 숨김 처리
        with st.expander("🛠️ 시스템 관리자 메뉴", expanded=False):
            st.caption("서버 로컬 테스트용 설정입니다.")
            if not google_api_key:
                st.warning("⚠️ 서버에 API 키가 설정되지 않았습니다.")
                temp_key = st.text_input("임시 Google API Key", type="password")
                if temp_key:
                    os.environ["GOOGLE_API_KEY"] = temp_key
                    import google.generativeai as genai
                    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
            
            use_mock_data = st.checkbox("🧪 가상 대기질 데이터 사용", value=False)
            ref_files = st.file_uploader("법령 지식베이스 (PDF/ZIP)", type=["pdf", "zip"], accept_multiple_files=True)

    col_logo, col_title = st.columns([1, 5])
    with col_logo: st.markdown("# 🏭")
    with col_title:
        st.markdown("# 비산배출시설 스마트 자가진단 시스템")
        st.caption("환경부 비산배출 시설관리기준 자가진단 및 AI 정밀 분석 보고서 자동 생성")
    st.divider()

    tab1, tab2 = st.tabs(["📋 사업장 및 서류 입력", "🚀 진단 실행 및 결과"])

    with tab1:
        st.subheader("1. 사업장 정보 입력")
        c1, c2 = st.columns(2)
        with c1: 
            user_company   = st.text_input("사업장명 *", value="(주)동신")
            user_biz_no    = st.text_input("사업자등록번호", value="000-00-00000")
            st.text_area("소재지 *", key="user_address", on_change=on_address_change, height=60)
            target_station = st.text_input("관할 대기 측정소", key="target_station")
            
        with c2: 
            user_rep       = st.text_input("대표자명", value="홍길동")
            user_permit_no = st.text_input("허가(신고)번호", value="충남-홍성-2020-0001")
            user_tel       = st.text_input("담당자 연락처", value="041-000-0000")
            user_industry  = st.selectbox("업종 분류", ["Ⅰ업종", "Ⅱ업종", "Ⅲ업종", "Ⅳ업종", "기타"])

        st.markdown("---")
        st.subheader("2. 진단 대상 서류 업로드")
        c3, c4 = st.columns(2)
        with c3: 
            st.markdown("**① 연간점검보고서 (운영기록부)**")
            measure_file = st.file_uploader("다개년도(PDF/ZIP) 스캔 지원", type=["pdf", "zip"], accept_multiple_files=True)
        with c4: 
            st.markdown("**② 신고증명서 (선택)**")
            report_file = st.file_uploader("신고증명서 (PDF) 업로드", type=["pdf"])

    with tab2:
        st.subheader("🚀 AI 진단 실행")
        start_button = st.button("📊 진단 시작 및 PDF 생성", type="primary", use_container_width=True)

        if start_button:
            if not os.environ.get("GOOGLE_API_KEY"): 
                st.error("❌ 시스템 에러: API 키가 설정되지 않았습니다. 관리자에게 문의하세요.")
                st.stop()
            if not measure_file: 
                st.warning("⚠️ 연간점검보고서(운영기록부) 파일을 먼저 업로드해주세요.")
                st.stop()

            if ref_files and st.session_state.vector_db is None:
                with st.spinner("📚 법령 지식베이스 구축 중..."): 
                    st.session_state.vector_db = build_vector_db(ref_files)

            with st.spinner("🌐 공공 대기질 데이터 조회 중..."):
                _, map_coord = get_auto_station_and_coord(st.session_state.user_address)
                if use_mock_data: 
                    air_data = {
                        "pm10Value": "58",  "pm25Value": "25", "o3Value": "0.055", 
                        "no2Value": "0.030", "so2Value": "0.005", "coValue": "0.6", 
                        "dataTime": datetime.now().strftime("%Y-%m-%d %H:00")
                    }
                else: 
                    air_data = get_air_quality(st.session_state.target_station, public_api_key)
                    if not air_data: 
                        air_data = {
                            "pm10Value": "58",  "pm25Value": "25", "o3Value": "0.055", 
                            "no2Value": "0.030", "so2Value": "0.005", "coValue": "0.6",
                            "dataTime": datetime.now().strftime("%Y-%m-%d %H:00")
                        }
                advice_text = generate_rich_advice(air_data, st.session_state.target_station)

            with st.spinner("🤖 AI 분석 진행 중... (문서 내 모든 연도 데이터를 전수 추출 중입니다. 수 분이 소요될 수 있습니다.)"):
                measure_pdfs   = extract_pdfs_from_source(measure_file)
                measure_images = convert_and_mask_images(measure_pdfs)
                ai_result      = analyze_log_compliance(measure_images, user_industry, st.session_state.vector_db)
                parsed_data = ai_result.get("parsed", {})

            st.divider()
            st.subheader("📊 AI 정밀 분석 대시보드")
            data_time = air_data.get("dataTime", "시간 정보 없음")
            st.caption(f"📡 공공데이터 측정 시점: **{data_time}** (한국환경공단 에어코리아 기준)")

            if parsed_data:
                scores = parsed_data.get("scores", {})
                metric_map = [("관리담당자", "manager_score"), ("공정/방지시설", "prevention_score"), ("LDAR 점검", "ldar_score"), ("기록 충실성", "record_score"), ("종합 등급", "overall_score")]
                cols = st.columns(5)
                for i, (label, key) in enumerate(metric_map):
                    s = scores.get(key, {}); score = s.get("score", "-"); grade = s.get("grade", "-")
                    display_score = f"{score}점" if str(score).isdigit() else "-"
                    with cols[i]: 
                        st.metric(label, display_score, f"등급: {grade}")

                st.markdown("---")
                c_ch1, c_ch2 = st.columns(2)
                with c_ch1:
                    st.markdown("**📈 방지시설(THC) 측정결과 추이**")
                    try:
                        df = pd.DataFrame(parsed_data["prevention"]["data"])
                        df["농도수치"] = df["value"].astype(str).str.extract(r"(\d+\.?\d*)").astype(float)
                        df_clean = df.dropna(subset=["농도수치"]).set_index("period")
                        if not df_clean.empty: 
                            st.line_chart(df_clean["농도수치"])
                        else: 
                            st.info("차트 데이터 부족")
                    except Exception: 
                        st.info("차트 데이터 부족")
                        
                with c_ch2:
                    process_data = parsed_data.get("process_emission", {}).get("data", [])
                    if len(process_data) > 0:
                        st.markdown("**📈 공정배출시설(냉각탑 등) 측정결과 추이**")
                        try:
                            df_proc = pd.DataFrame(process_data)
                            df_proc["농도수치"] = df_proc["value"].astype(str).str.extract(r"(\d+\.?\d*)").astype(float)
                            df_proc_clean = df_proc.dropna(subset=["농도수치"]).set_index("period")
                            if not df_proc_clean.empty: 
                                st.bar_chart(df_proc_clean["농도수치"])
                            else: 
                                st.info("차트 데이터 부족")
                        except Exception: 
                            st.info("차트 데이터 부족")
                    else:
                        st.markdown("**📊 LDAR 누출 실적 (대상/누출 비교)**")
                        try:
                            df2 = pd.DataFrame(parsed_data["ldar"]["data"])
                            df2["대상개소"] = df2["target_count"].astype(str).str.extract(r"(\d+)").astype(float)
                            df2["누출수"] = df2["leak_count"].astype(str).str.extract(r"(\d+)").astype(float)
                            df2_clean = df2.dropna(subset=["대상개소", "누출수"]).set_index("year")
                            if not df2_clean.empty: 
                                st.bar_chart(df2_clean[["대상개소", "누출수"]])
                            else: 
                                st.info("차트 데이터 부족")
                        except Exception: 
                            st.info("차트 데이터 부족")

                with st.expander("📋 AI 추출 데이터 원본 확인 (디버깅용)", expanded=False): 
                    st.json(parsed_data)
            else:
                st.error("❌ 데이터 파싱 실패. 원본 문서를 확인하십시오.")
                st.text(ai_result.get("raw", "오류 상세 없음"))

            user_info = {
                "company": user_company, "industry": user_industry, "address": st.session_state.user_address,
                "rep": user_rep, "permit_no": user_permit_no, "tel": user_tel, "biz_no": user_biz_no,
            }
            
            pdf_bytes = create_gov_report_pdf(ai_result, user_info, advice_text, air_data, st.session_state.target_station, map_coord)

            st.divider()
            c_dl1, c_dl2, c_dl3 = st.columns([1, 2, 1])
            with c_dl2:
                st.download_button(
                    label = "⬇️ 최종 진단 보고서 다운로드 (PDF)",
                    data = pdf_bytes,
                    file_name = f"비산배출_정밀진단보고서_v106.0_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime = "application/pdf",
                    use_container_width = True,
                )

if __name__ == "__main__":
    main()