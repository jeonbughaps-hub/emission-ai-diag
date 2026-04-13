def analyze_log_compliance(measure_images, user_industry: str, vector_db):
    if not os.environ.get("GOOGLE_API_KEY") or not measure_images: 
        return {"parsed": {}, "raw": ""}

    from utils import get_limit_ppm
    model = get_model()
    limit_text = get_limit_ppm(user_industry)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    rag_context = ""
    if vector_db:
        try:
            docs = vector_db.similarity_search(f"{user_industry} 시설관리기준", k=3)
            rag_context = "\n".join([d.page_content for d in docs])
        except: pass

    # ★ 핵심 수정: PDF가 깨지지 않도록 JSON 구조와 규칙을 극도로 엄격하게 통제
    prompt = f"""
당신은 환경부 비산배출시설 전문 진단 엔진입니다. (시점: {current_time})
업종: {user_industry} | THC 기준: {limit_text}

[판정 논리 및 절대 지켜야 할 규칙]
1. 빈 데이터 처리 (매우 중요): 데이터가 없다면 반드시 빈 배열 `[]`만 반환하세요. 절대 배열 안에 "데이터 없음", "추출 불가" 등의 텍스트를 넣지 마세요.
2. 반기 분리: 표에서 상/하반기 수치가 뭉쳐있으면 반드시 2개의 행으로 분리하세요.
3. 부적합 판정: 측정값이 {limit_text}를 단 0.01이라도 넘으면 무조건 result를 '부적합'으로 하세요.
4. 항목 누락 금지: 'risk_matrix'와 'improvement_roadmap'은 데이터가 부족하더라도 일반적인 환경관리 권고안을 만들어서 최소 1개 이상 반드시 채워 넣으세요.

[JSON 구조 - 아래 지정된 Key를 1글자도 틀리지 말고 사용할 것]
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":100, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"A"}}, "overall_score": {{"score":97, "grade":"A"}} }},
  "manager": {{ "data": [ {{"period": "연도", "name": "이름", "dept": "부서", "date": "선임일", "qualification": "자격"}} ] }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "측정일", "facility": "시설명", "value": "농도", "limit": "{limit_text}", "result": "적합/부적합"}} ] }},
  "process_emission": {{ "data": [] }},
  "ldar": {{ "data": [ {{"year": "연도", "target_count": "0", "leak_count": "0", "leak_rate": "0%", "result": "적합/부적합"}} ] }},
  "risk_matrix": [ {{"item": "방지시설 효율 저하", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 정밀 점검 및 교체 주기 확인", "expected_effect": "배출 농도 안정화"}} ],
  "overall_opinion": "법령 근거 중심의 상세 보고서 (\\n 사용)"
}}
"""
    try:
        import gc
        gc.collect()
        response = model.generate_content([prompt, *measure_images])
        raw_text = response.text
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}')
        parsed_data = json.loads(raw_text[start_idx:end_idx+1], strict=False) if start_idx != -1 else {}

        # ★ 2차 방어선: AI가 실수로 텍스트를 넣었을 경우 강제로 빈 배열로 초기화
        for key in ["manager", "prevention", "process_emission", "ldar"]:
            if key in parsed_data and isinstance(parsed_data[key], dict) and "data" in parsed_data[key]:
                # data 안의 요소가 딕셔너리가 아닌 단순 문자열("데이터 없음" 등)이면 날려버림
                if any(isinstance(item, str) for item in parsed_data[key]["data"]):
                    parsed_data[key]["data"] = []
            elif key in parsed_data and isinstance(parsed_data[key], list):
                if any(isinstance(item, str) for item in parsed_data[key]):
                    parsed_data[key] = {"data": []}
                else:
                    parsed_data[key] = {"data": parsed_data[key]}
            else:
                parsed_data[key] = {"data": []}
                
        # 매트릭스와 로드맵 2차 방어선
        for key in ["risk_matrix", "improvement_roadmap"]:
            if key not in parsed_data or not isinstance(parsed_data[key], list):
                parsed_data[key] = []
                
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        return {"parsed": {}, "raw": str(e)}
