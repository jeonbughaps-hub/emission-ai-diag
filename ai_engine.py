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
import zipfile  # 🚨 추가: ZIP 파일 처리를 위한 내장 라이브러리

warnings.filterwarnings("ignore", category=FutureWarning)

# =====================================================================
# ★ 업그레이드: 일반 PDF 및 ZIP 파일 내 PDF 자동 추출 로직
# =====================================================================
def extract_pdfs_from_source(uploaded_files):
    pdf_list = []
    if not uploaded_files: return pdf_list
    if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
    
    for uf in uploaded_files:
        file_name = uf.name.lower()
        
        # 1. 단일 PDF 파일인 경우
        if file_name.endswith(".pdf"):
            pdf_list.append((uf.name, uf))
            
        # 2. ZIP 압축 파일인 경우
        elif file_name.endswith(".zip"):
            try:
                # 서버 용량 낭비 없이 메모리(RAM) 상에서 즉시 압축 해제
                with zipfile.ZipFile(io.BytesIO(uf.read())) as z:
                    for inner_file in z.namelist():
                        # Mac OS 환경에서 압축 시 생성되는 불필요한 숨김 파일 배제
                        if "__MACOSX" in inner_file or inner_file.split("/")[-1].startswith("."): 
                            continue
                            
                        # ZIP 내부의 파일이 PDF일 경우에만 추출
                        if inner_file.lower().endswith(".pdf"):
                            pdf_bytes = z.read(inner_file)
                            # 일반 파일 객체(Streamlit UploadedFile)처럼 행동하도록 BytesIO로 래핑
                            pdf_list.append((inner_file, io.BytesIO(pdf_bytes)))
            except Exception as e:
                st.error(f"ZIP 파일 '{uf.name}' 압축 해제 중 오류가 발생했습니다: {e}")
                
    return pdf_list

def convert_and_mask_images(pdf_list):
    all_images = []
    my_bar = st.progress(0.1, text="PDF 문서 정밀 스캔 및 이미지 변환 중...")
    for idx, (name, fbytes) in enumerate(pdf_list):
        try:
            fbytes.seek(0)
            doc = fitz.open(stream=fbytes.read(), filetype="pdf")
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8))
                img = Image.open(io.BytesIO(pix.tobytes("jpeg", 75)))
                if img.mode != 'RGB': img = img.convert('RGB')
                all_images.append(img)
                del pix
            doc.close()
        except Exception: continue
    gc.collect()
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

    prompt = f"""당신은 환경부 비산배출시설 기술진단 전문 엔진입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[★ 최우선 지시사항 : 데이터 전수 추출 및 팩트 체크 ★]
1. 방지시설 농도 (prevention):
   - 문서에 명확히 기록된 횟수와 수치만 정확히 추출하세요.
   - 단일 시설에 대해 1번만 측정되었다면 반드시 1건만 배열에 담아야 합니다. (절대 중복으로 추출하거나, 없는 데이터를 추론해서 2개 이상으로 부풀리지 마세요.)
2. LDAR 누출 점검 (ldar):
   - '대상 개소(target_count)'는 문서에 나열된 전체 설비/부품의 총 목록 개수가 **아닙니다.**
   - 해당 연도 기록지에서 '실제로 측정(점검)을 수행하여 측정값이 존재하는 개소 수'만 정확히 카운트하여 기재하세요. (빈칸이거나 점검하지 않은 대상은 제외)

[전문 종합 의견 작성 지침]
- 4가지 소제목을 사용하여 800자 내외로 상세하게 작성하세요.
   【1. 시설관리 종합 평가】, 【2. 방지시설 효율성 분석】, 【3. LDAR 점검 이행 평가】, 【4. 중장기 관리 권고 사항】

[출력 JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"B"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "추출날짜", "facility": "추출시설명", "value": "추출농도", "limit": "{limit_text}", "result": "적합/부적합"}} ] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "실제측정개소수", "leak_count": "누출수", "leak_rate": "0%", "recheck_done": "이행완료", "result": "적합"}} ] }},
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
        parsed_data = json.loads(re.search(r'\{.*\}', raw_text, re.DOTALL).group(0), strict=False)
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
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

def build_vector_db(uploaded_files=None, location_key="default"):
    return None
