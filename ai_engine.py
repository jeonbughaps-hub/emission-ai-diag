import os
import fitz
import google.generativeai as genai
from PIL import Image
import io
import json
import streamlit as st
import gc

def get_model():
    return genai.GenerativeModel("gemini-2.0-flash")

# 서버 지식베이스 자동 로딩
def build_vector_db():
    # (기존 서버 폴더 knowledge_base 읽기 로직 유지)
    # ...생략 (이전 답변의 build_vector_db 전체 코드 사용)...
    pass

def analyze_log_compliance(measure_images, user_industry, vector_db):
    model = get_model()
    
    # ★ 프롬프트 강화: 공공기관 보고서 형식의 풍부한 내용 요청
    prompt = f"""
당신은 대한민국 환경부 및 한국환경공단 소속의 '비산배출시설 기술진단 전문관'입니다. 
사업장의 운영기록부를 정밀 분석하여 정부 보고서 규격에 맞는 고품질 진단 의견을 작성하세요.

[필수 작성 지침]
1. 분량: 'overall_opinion' 항목은 반드시 2000자 이상의 상세한 분석으로 채우세요.
2. 구성: 
   - 1. 시설 관리 현황 총평
   - 2. 다개년 배출 농도 추이 정밀 분석 (수치 인용 필수)
   - 3. 법규 준수 여부 및 잠재적 리스크 분석 (대기환경보전법 조항 언급)
   - 4. 기술적 개선 권고 (흡착제 교체, LDAR 고도화 등)
3. 어조: 매우 전문적이고 격식 있는 공공기관 보고서 톤을 유지하세요.

[JSON 구조]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":100, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":97, "grade":"A"}} }},
  "manager": {{ "data": [] }},
  "prevention": {{ "data": [] }},
  "ldar": {{ "data": [] }},
  "risk_matrix": [],
  "improvement_roadmap": [],
  "overall_opinion": "여기에 2000자 이상의 정밀 보고서 작성 (줄바꿈은 \\n 사용)"
}}
"""
    # (이후 분석 및 JSON 추출 로직 유지)
    # ...
