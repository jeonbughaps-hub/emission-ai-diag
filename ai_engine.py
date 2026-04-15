import os
from google import genai
from google.genai import types
import json
import re
import streamlit as st
from datetime import datetime
import tempfile
import time
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

KB_DIRECTORY = "knowledge_base/"

def extract_pdfs_from_source(uploaded_files):
    pdf_list = []
    if not uploaded_files: return pdf_list
    if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
    for uf in uploaded_files:
        if uf.name.lower().endswith(".pdf"):
            pdf_list.append((uf.name, uf))
    return pdf_list

@st.cache_resource(show_spinner="지식베이스 로딩 중...")
def build_vector_db(uploaded_files=None, location_key="default"):
    return None

def convert_and_mask_images(pdf_list):
    # 4/13 성공 버전처럼 별도 이미지 변환 없이 원본을 그대로 넘깁니다.
    return pdf_list

def analyze_log_compliance(pdf_list, user_industry: str, vector_db):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not pdf_list: 
        return {"parsed": {}, "raw": ""}

    client = genai.Client(api_key=api_key)
    from utils import get_limit_ppm
    limit_text = get_limit_ppm(user_industry)
    
    my_bar = st.progress(0.1, text="원본 파일을 분석기로 전송 중입니다...")
    
    gfiles = []

    # =====================================================================
    # ★ 4/13 성공 로직: 파일을 쪼개거나 변환하지 않고 원본 그대로 업로드
    # =====================================================================
    for name, uf in pdf_list:
        try:
            uf.seek(0)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uf.read())
                tmp_path = tmp.name
            
            # 구글 서버로 직접 업로드 (가장 단순한 방식)
            gfile = client.files.upload(file=tmp_path, config={'display_name': name})
            
            # 업로드 완료 대기
            wait_count = 0
            while "PROCESSING" in str(gfile.state) and wait_count < 60:
                time.sleep(2)
                gfile = client.files.get(name=gfile.name)
                wait_count += 1
                
            if "ACTIVE" in str(gfile.state):
                gfiles.append(gfile)
            os.remove(tmp_path)
            
        except Exception as e:
            st.error(f"파일 업로드 실패: {e}")
            continue

    if not gfiles:
        my_bar.empty()
        return {"parsed": {}, "raw": "분석 준비 실패"}

    my_bar.progress(0.6, text="🚀 AI가 전체 데이터를 분석 중입니다. 잠시만 기다려주세요...")

    # 4/13 당시에 사용했던 가장 표준적인 프롬프트
    prompt = f"""당신은 환경부 소속 '비산배출시설 기술진단 전문관'입니다.
첨부된 운영기록부 원본(통합 파일)을 전수 조사하여 아래 데이터를 추출하고 진단 결과를 작성하세요.

업종 기준: {limit_text}

[추출 및 작성 규칙]
1. 모든 페이지를 정독하여 방지시설 농도 기록과 LDAR 점검 실적을 찾으세요.
2. LDAR 점검 기록은 개별 행을 나열하지 말고, 전체 점검 개소 합계와 기준 초과(누출) 건수만 단 1줄로 요약하세요.
3. 마스킹되어 보이지 않는 정보는 "-" 또는 "확인불가"로 표기하여 무조건 표를 채우세요.

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "담당자", "dept": "부서", "date": "날짜", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "날짜", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "총 개수", "leak_count": "초과 건수", "leak_rate": "0%", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "시설 관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "점검 강화", "expected_effect": "안정성 확보"}} ],
  "overall_opinion": "종합 의견 상세 작성"
}}
"""
    try:
        # 화학물질 관련 차단을 막기 위한 최소한의 안전 설정
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
        
        contents = [prompt] + gfiles
        
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                safety_settings=safety_settings
            )
        )
        
        raw_text = response.text.strip()
        parsed_data = {}
        
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            try: 
                parsed_data = json.loads(match.group(0), strict=False)
            except Exception:
                pass

        # 최소한의 데이터 유효성 검사 (UI 붕괴 방지)
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key not in parsed_data or not isinstance(parsed_data[key], dict) or "data" not in parsed_data[key]:
                parsed_data[key] = {"data": []}

        if not parsed_data.get("scores"):
            parsed_data["scores"] = {"manager_score": {"score": 0, "grade": "F"}, "prevention_score": {"score": 0, "grade": "F"}, "ldar_score": {"score": 0, "grade": "F"}, "record_score": {"score": 0, "grade": "F"}, "overall_score": {"score": 0, "grade": "F"}}

        my_bar.empty()
        return {"parsed": parsed_data, "raw": raw_text}

    except Exception as e:
        st.error(f"분석 중 오류 발생: {e}")
        fallback_data = {"scores": {}, "manager": {"data": []}, "prevention": {"data": []}, "process_emission": {"data": []}, "ldar": {"data": []}, "risk_matrix": [], "improvement_roadmap": [], "overall_opinion": str(e)}
        my_bar.empty()
        return {"parsed": fallback_data, "raw": str(e)}
    finally:
        for gf in gfiles:
            try: client.files.delete(name=gf.name)
            except: pass
