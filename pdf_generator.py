def analyze_log_compliance(measure_images, user_industry: str, vector_db):
    api_key = get_api_key()
    if not api_key: 
        st.error("API 키를 찾을 수 없습니다. Secrets 설정을 확인하세요.")
        return {"parsed": {}, "raw": "API 키 오류"}
            
    client = genai.Client(api_key=api_key)
    
    industry_str = str(user_industry).upper()
    if any(x in industry_str for x in ["3", "III", "Ⅲ", "4", "IV", "Ⅳ"]):
        limit_text = "100ppm"
    else:
        limit_text = "50ppm"
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    retrieved_knowledge = ""
    if vector_db is not None:
        try:
            search_query = f"비산배출시설 {user_industry} 방지시설 냉각탑 열교환기 관리기준 및 행정처분"
            docs = vector_db.similarity_search(search_query, k=4)
            retrieved_knowledge = "\n".join([doc.page_content for doc in docs])
        except:
            retrieved_knowledge = ""

    prompt = f"""당신은 환경부 비산배출시설 기술진단 전문 AI입니다. (시점: {current_time})
대상 업종: {user_industry} | 적용 배출기준: {limit_text}

[★ 최우선 지시사항 : 데이터 100% 전수조사 추출 ★]
1. 첨부된 모든 문서/이미지를 스캔하여 아래 데이터를 찾아 배열에 담으세요.
2. 방지시설 농도 (prevention): '측정일시', '시설명', '측정결과 후단' 칼럼의 값을 추출하세요. (THC 측정기기 정도검사 결과는 제외)
3. LDAR 누출 점검 (ldar): 2022년, 2023년, 2024년, 2025년 등 문서에 존재하는 '모든 연도'의 점검 실적을 단 한 해도 빼놓지 말고 전수조사하여 각각 추출하세요.

[🚨 냉각탑 및 열교환기 정밀 분석 필수 - 연도별 누락 절대 금지 🚨]
문서 내에 '냉각탑(Cooling Tower)' 또는 '열교환기(Heat Exchanger)'와 관련된 연 1회 점검 기록이 있는지 반드시 확인하고, 발견되면 `cooling` 객체의 `data` 배열에 담으세요.
- ❗️가장 중요: 2022년, 2023년, 2024년, 2025년 등 과거 연도의 데이터가 존재한다면 '절대 중간 연도를 빼먹지 말고' 모든 연도의 점검 기록을 개별 행(객체)으로 전부 추가해야 합니다. (AI 모델의 임의 요약 및 스킵을 엄격히 금지합니다)
- 측정 날짜(date)를 반드시 추출하여 `date` 속성에 기입하세요. (예: "2024-05-12")
- 냉각탑: 냉각수 TOC 분석 실시 여부 및 TOC 농도 50ppm 미만 유지 여부 (초과 시 부적합)
- 열교환기: 전·후단 냉각수 농도 편차 분석 실시 여부 및 편차 1ppm 미만 또는 10% 미만 유지 여부 (초과 시 부적합)
📌 [특수 계산 조건]: 만약 열교환기 항목에 측정 수치가 하나만 기재되어 있다면, 이는 '후단' 수치로 간주합니다. 이 경우 해당 연도의 '냉각탑 TOC 분석 결과값'을 찾아 열교환기의 '전단' 수치로 대입하여 두 수치의 편차를 직접 계산하세요.

[🚫 강력한 환각(Hallucination) 방지 지시사항 🚫]
서술형 의견(overall_opinion 등)을 작성할 때, 문서에서 실제로 추출된 연도, 시설명, 수치만을 100% 팩트 기반으로 서술하세요. 문서에 없는 과거 이력을 상상하거나 지어내지 마십시오.

[★ 지식베이스 ★]
{retrieved_knowledge if retrieved_knowledge else "기본 환경 지식 활용"}

[★ 출력 형식 ★]
반드시 마크다운 없이 순수 JSON 객체로만 출력하세요. 속성명과 구조를 절대 바꾸지 마세요.
{{
  "scores": {{ "manager_score": {{"score":100, "grade":"A"}}, "prevention_score": {{"score":95, "grade":"A"}}, "ldar_score": {{"score":100, "grade":"A"}}, "record_score": {{"score":90, "grade":"B"}}, "overall_score": {{"score":96, "grade":"A"}} }},
  "prevention": {{ "data": [ {{"period": "반기", "date": "2025-05-26", "facility": "흡착에의한시설(7)", "value": "5.4", "limit": "{limit_text}", "result": "적합"}} ] }},
  "ldar": {{ "data": [ {{"year": "2025", "target_count": "10", "leak_count": "0", "leak_rate": "0%", "recheck_done": "이행완료", "result": "적합"}} ] }},
  "cooling": {{ "data": [
    {{"date": "2023-04-10", "facility": "냉각탑", "value": "2.6ppm", "limit": "50ppm 미만", "result": "적합"}},
    {{"date": "2024-05-12", "facility": "열교환기(CK-1)", "value": "편차 0.1ppm", "limit": "1ppm 미만", "result": "적합"}}
  ]}},
  "risk_matrix": [ {{"item": "시설관리", "probability": "보통", "impact": "높음", "priority": "Medium"}} ],
  "improvement_roadmap": [ {{"phase": "단기", "action": "시설 점검 강화", "expected_effect": "효율 안정화"}} ],
  "priority_actions": [ {{"priority": "1", "action": "냉각탑 TOC 정기검사", "deadline": "1개월 이내", "owner": "환경안전팀"}} ],
  "law_references": [ {{"law_name": "비산배출시설 관리기준", "article": "관련 조문", "summary": "냉각수 TOC 50ppm 미만 유지 의무", "checked_date": "2026-10-18"}} ],
  "followup_actions": [ {{"action": "열교환기 편차 점검", "owner": "관리자", "deadline": "분기 내", "status": "대기"}} ],
  "overall_opinion": "반드시 추출된 실제 데이터만을 기반으로 작성. 절대 가상의 과거 이력을 지어내지 말 것."
}}
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt] + measure_images,
            config=types.GenerateContentConfig(temperature=0.0)
        )
        
        raw_text = response.text.strip()
        
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()
            
        try:
            parsed_data = json.loads(raw_text, strict=False)
        except:
            match = re.search(r'\{.*\}', raw_text.replace('\n', ''), re.DOTALL)
            if match:
                parsed_data = json.loads(match.group(0), strict=False)
            else:
                parsed_data = {}
                
        return {"parsed": parsed_data, "raw": raw_text}
    except Exception as e:
        st.error(f"1단계 데이터 추출 중 API 오류 발생: {e}")
        return {"parsed": {}, "raw": f"에러 발생: {e}"}
