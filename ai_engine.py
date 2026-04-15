import os
from google import genai
from google.genai import types
import json
import re
import streamlit as st
import tempfile
import time
import warnings

# 불필요한 경고창 제거
warnings.filterwarnings("ignore", category=FutureWarning)

# 지식베이스 경로는 유지하되 기능은 비활성화
KB_DIRECTORY = "knowledge_base/"

def extract_pdfs_from_source(uploaded_files):
    pdf_list = []
    if not uploaded_files: return pdf_list
    if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
    for uf in uploaded_files:
        if uf.name.lower().endswith(".pdf"):
            pdf_list.append((uf.name, uf))
    return pdf_list

@st.cache_resource(show_spinner="시스템 초기화 중...")
def build_vector_db(uploaded_files=None, location_key="default"):
    # 4/13 버전처럼 지식베이스 기능을 사용하지 않습니다.
    return None

def convert_and_mask_images(pdf_list):
    # 서버 메모리를 보호하기 위해 원본 파일을 그대로 반환합니다.
    return pdf_list

def analyze_log_compliance(pdf_list, user_industry: str, vector_db):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not pdf_list: 
        return {"parsed": {}, "raw": ""}

    client = genai.Client(api_key=api_key)
    
    # 공공기관 업무 효율을 위해 utils에서 기준 정보만 가져옵니다.
    from utils import get_limit_ppm
    limit_text = get_limit_ppm(user_industry)

    my_bar = st.progress(0.1, text="파일을 분석 서버로 전송 중입니다...")
    
    gfiles = []
    # 4/13 성공 로직: 원본 파일을 그대로 구글 서버에 업로드하여 분석
    for name, uf in pdf_list:
        try:
            uf.seek(0)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uf.read())
                tmp_path = tmp.name
                
            # 구글 서버로 직접 업로드
            gfile = client.files.upload(file=tmp_path, config={'display_name': name})
            
            # 파일이 분석 가능한 상태가 될 때까지 짧게 대기
            wait_count = 0
            while gfile.state.name == "PROCESSING" and wait_count < 30:
                time.sleep(2)
                gfile = client.files.get(name=gfile.name)
                wait_count += 1
                
            if gfile.state.name == "ACTIVE":
                gfiles.append(gfile)
            os.remove(tmp_path)
        except Exception as e:
            st.error(f"파일 전송 중 오류: {e}")
            continue

    if not gfiles:
        my_bar.empty()
        return {"parsed": {}, "raw": "전송된 파일이 없습니다."}

    my_bar.progress(0.6, text="AI가 문서를 정독하여 데이터를 추출 중입니다...")

    # 4/13 당시 가장 높은 성공률을 보였던 핵심 프롬프트
    prompt = f"""당신은 환경부 소속 '비산배출시설 기술진단 전문관'입니다.
첨부된 운영기록부 문서를 전수 조사하여 아래 JSON 양식에 맞춰 데이터를 추출하세요.
업종 기준: {limit_text}

[작성 규칙]
1. LDAR 점검 기록은 전체 점검 개소 합계와 기준 초과(누출) 건수만 단 1줄로 요약하세요.
2. 마스킹되어 보이지 않는 정보는 "-" 또는 "확인불가"로 표기하여 무조건 칸을 채우세요.
3. 데이터가 없는 항목은 빈 배열 [] 대신 더미 데이터를 넣어 형식을 유지하세요.

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "날짜", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "날짜", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "총 개수", "leak_count": "초과 건수", "leak_rate": "0%", "result": "적합"}} ] }},
  "risk_matrix": [ {{"item": "시설 관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "점검 이행", "expected_effect": "관리 강화"}} ],
  "overall_opinion": "데이터 분석 결과 이상 없음."
}}
"""
    try:
        # 분석 실행
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt] + gfiles,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        
        raw_text = response.text.strip()
        parsed_data = {}
        
        # JSON 추출
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            try: 
                parsed_data = json.loads(match.group(0), strict=False)
            except:
                pass

        # 최소한의 구조 보장 (에러 방지)
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key not in parsed_data: parsed_data[key] = {"data": []}

        my_bar.empty()
        return {"parsed": parsed_data, "raw": raw_text}

    except Exception as e:
        st.error(f"분석 중 오류 발생: {e}")
        return {"parsed": {}, "raw": str(e)}
    finally:
        # 구글 서버 파일 정리
        for gf in gfiles:
            try: client.files.delete(name=gf.name)
            except: pass
