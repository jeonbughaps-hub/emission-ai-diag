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

warnings.filterwarnings("ignore", category=FutureWarning)

FAISS_DB_DIR = "faiss_vector_db"

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

    # 💡 JSON 파싱 오류를 원천 차단하기 위해 스키마 정의를 추가
    response_schema = {
        "type": "object",
        "properties": {
            "scores": {
                "type": "object",
                "properties": {
                    "manager_score": {"type": "object", "properties": {"score": {"type": "integer"}, "grade": {"type": "string"}}},
                    "prevention_score": {"type": "object", "properties": {"score": {"type": "integer"}, "grade": {"type": "string"}}},
                    "ldar_score": {"type": "object", "properties": {"score": {"type": "integer"}, "grade": {"type": "string"}}},
                    "record_score": {"type": "object", "properties": {"score": {"type": "integer"}, "grade": {"type": "string"}}},
                    "overall_score": {"type": "object", "properties": {"score": {"type": "integer"}, "grade": {"type": "string"}}}
                }
            },
            "prevention": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "period": {"type": "string"},
                                "date": {"type": "string"},
                                "facility": {"type": "string"},
                                "value": {"type": "string"},
                                "limit": {"type": "string"},
                                "result": {"type": "string"}
                            }
                        }
                    }
                }
            },
            "ldar": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "year": {"type": "string"},
                                "target_count": {"type": "string"},
                                "leak_count": {"type": "string"},
                                "leak_rate": {"type": "string"},
                                "recheck_done": {"type": "string"},
                                "result": {"type": "string"}
                            }
                        }
                    }
                }
            },
            "cooling": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "date": {"type": "string"},
                                "facility": {"type": "string"},
                                "value": {"type": "string"},
                                "limit": {"type": "string"},
                                "result": {"type": "string"}
                            }
                        }
                    }
                }
            },
            "risk_matrix": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item": {"type": "string"},
                        "probability": {"type": "string"},
                        "impact": {"type": "string"},
                        "priority": {"type": "string"}
                    }
                }
            },
            "improvement_roadmap": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "phase": {"type": "string"},
                        "action": {"type": "string"},
                        "expected_effect": {"type": "string"}
                    }
                }
            },
            "overall_opinion": {"type": "string"}
        }
    }

    prompt = f"""당신은 환경부 비산배출시설 기술진단 전문 AI입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[★ 최우선 지시사항 : 데이터 100% 전수조사 추출 ★]
1. 첨부된 모든 문서/이미지를 스캔하여 아래 데이터를 찾아 배열에 담으세요.

2. 방지시설 농도 (prevention): 문서에 기록된 '실제 측정일자', '시설명', '측정결과(전단/후단)' 값을 추출하세요.
   - 🚨 시설명 텍스트 정제: PDF 인식 오류로 글자가 깨진 경우 문맥에 맞게 깔끔한 이름으로 정제하세요.
   - 🚨 날짜(date) 추출 경고: 해당 데이터의 '실제 측정 연도와 월'을 혼동하지 마세요.
   - 🚨 결과(value) 양식: 전·후단 측정 시 "전단: OOppm, 후단: OOppm (효율 OO%)", 후단만 측정 시 "후단: OOppm"
   - 🚨 저감효율 예외 판정: 측정값이 {ppm_limit}ppm을 초과하더라도, 문서상 '저감효율'이 {eff_limit}% 이상인 경우 최종 판정(result)은 반드시 '적합'으로 처리하세요.

3. LDAR 누출 점검 (ldar): 문서에 '실제로 기록되어 있는 연도별' 점검 실적을 추출하세요. 
   - 🚨 연도 환각 엄격 금지: 업로드된 문서에 존재하는 연도(예: 23~25년)의 데이터만 추출하세요. 문서에 없는 과거 연도(예: 2022년 등)는 절대 임의로 지어내어 생성하지 마십시오.
   - 🚨 연도별 데이터 합산(Aggregation) 필수: 동일 연도에 여러 공정/시설의 점검 기록이 여러 줄로 나뉘어 있다면, 반드시 해당 연도의 '대상 개소(target_count)'와 '누출 수(leak_count)'를 모두 더하여 연도별로 딱 1개의 객체(행)만 생성하세요.
   - 🚨 비산누출시설 판정(result) 핵심 규칙 🚨:
     > 누출 수(leak_count)가 0건이면 "누출 없음"으로 기록하고 무조건 "적합" 판정하세요. 절대 누출이 발생했다고 지어내지 마세요.
     > 누출 수(leak_count)가 1건 이상 발생했더라도, '누출발생 시점으로 30일 이내 재조치 완료 후 운영기록부 기록' 내용이 확인되면 최종 판정은 반드시 "적합"으로 처리하세요.

[🚨 냉각탑 및 열교환기 정밀 분석 필수 - 환각 엄격 금지 🚨]
- ❗️문서에 냉각탑이나 열교환기 관련 점검 기록이 실제로 존재하는 경우에만 추출하여 `cooling` 배열에 담으세요.
- ❗️만약 관련 기록이 전혀 없다면, 절대 지어내지 말고 `cooling` 배열을 빈 배열(`[]`)로 비워두세요.

[🚫 강력한 환각(Hallucination) 방지 지시사항 🚫]
서술형 종합 의견(overall_opinion)을 작성할 때, 누출 수(leak_count)가 0건인데도 "누출이 발생했다"고 반대로 적거나, 문서에 없는 과거 연도를 언급하는 치명적인 환각을 절대 저지르지 마세요.

[★ 지식베이스 ★]
{retrieved_knowledge if retrieved_knowledge else "기본 환경 지식 활용"}
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt] + measure_images,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=response_schema
            )
        )
        
        raw_text = response.text.strip()
        parsed_data = json.loads(raw_text)
        return {"parsed": parsed_data, "raw": raw_text}
    
    except Exception as e:
        st.error(f"1단계 데이터 추출 중 오류 발생: {e}")
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
        st.error(f"2단계 전문가 제언 중 오류 발생: {e}")
        return "AI 모델 통신 오류로 전문가 제언 생성을 일시 생략합니다."
