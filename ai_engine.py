# ai_engine.py 내 analyze_log_compliance 함수의 프롬프트 부분 수정

    industry_str = str(user_industry).upper()
    if any(x in industry_str for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]):
        limit_val = 100
        limit_text = "100ppm"
    else:
        limit_val = 50
        limit_text = "50ppm"

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ★ 핵심 지시: 의견을 기술적이고 풍부하게 작성하라고 명령
    prompt = f"""당신은 환경부 비산배출시설 기술진단 전문 엔진입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[진단 지시사항]
- 운영기록부 이미지를 분석하여 법규 준수 여부를 정밀 진단하세요.
- 단순히 나열하지 말고 아래 4가지 소제목을 사용하여 전문가 톤으로 아주 풍부하게(1,000자 내외) 작성하세요.
  【1. 시설관리 총평】: 전반적인 등급 부여 근거와 사업장의 환경관리 수준 진단.
  【2. 방지시설 운영 효율 분석】: 측정된 THC 수치와 기준치({limit_text}) 대비 안정성 평가.
  【3. LDAR 및 누출 관리 현황】: 점검 누락 여부, 누출률 관리 상태 및 보수 적정성 평가.
  【4. 향후 정기점검 대비 관리 권고】: 정기점검 및 환경청 점검 대비 중점 관리 요소 및 제언.

[출력 JSON 구조]
{{
  "scores": {{ 
    "manager_score": {{"score":100, "grade":"A", "reason":"적정"}}, 
    "prevention_score": {{"score":95, "grade":"A", "reason":"준수"}}, 
    "ldar_score": {{"score":100, "grade":"A", "reason":"양호"}}, 
    "record_score": {{"score":90, "grade":"B", "reason":"보통"}}, 
    "overall_score": {{"score":96, "grade":"A"}} 
  }},
... (이하 기존과 동일) ...
"""
