# ai_engine.py 파일 내의 generate_advanced_air_advice 함수 부분을 이걸로 교체해 주세요!

def generate_advanced_air_advice(station_name: str, pm10_val: str, o3_val: str):
    """
    단순한 수치 안내를 넘어, VOCs(유기물질)가 오존 및 미세먼지에 
    미치는 광화학적 영향을 엮어 700자 이상의 전문적인 조언을 생성합니다.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key: return "대기질 정보를 불러올 수 없습니다."
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
당신은 환경부 및 국립환경과학원 수준의 대기환경 전문 연구원입니다.
관할 측정소({station_name})의 현재 실시간 대기질은 미세먼지(PM10): {pm10_val} ㎍/m³, 오존(O3): {o3_val} ppm 입니다.
이 사업장은 인쇄, 코팅 등에서 '유기용제(VOCs)'를 다량 취급하는 비산배출시설입니다.

아래 3가지 소제목을 사용하여 **총 700자~800자 분량**의 아주 깊이 있고 전문적인 '환경 관리 지침'을 작성하세요.
단순 요약이 아닌, 논리적이고 구체적인 대응 방안을 서술해야 합니다.

【1. 지역 대기질 현황 및 광화학적 영향 분석】 (약 250자 이상)
- 현재 지역의 오존/미세먼지 수치의 위험도를 평가하세요.
- 사업장에서 배출되는 유기용제(VOCs)가 질소산화물(NOx)과 광화학 반응을 일으켜 오존(O3)을 생성하고, 2차 유기 에어로졸(SOA)로 변환되어 미세먼지를 가중시킨다는 점을 과학적 원리에 기반하여 설명하세요.

【2. 현장 비산배출원 선제적 통제 가이드】 (약 250자 이상)
- 실질적인 공정 운영 관리 방안을 제시하세요.
- 오후 피크타임(14~16시) 유기용제 고농도 작업 시간대 조정, 옥외 하역 및 이송 시 밀폐 조건, 혼합 과정에서의 원천적 누출 차단 등 구체적인 가이드를 제공하세요.

【3. 방지시설 및 LDAR 연계 집중 관리 방안】 (약 250자 이상)
- 활성탄 흡착탑 등 대기오염 방지시설의 처리 효율 최적화를 위한 차압 관리 및 교체 주기 준수 방안을 제시하세요.
- 회전/연결 기기(플랜지, 밸브, 펌프 등)에 대한 선제적 LDAR(누출탐지 및 보수) 활동 강화 지시를 포함하세요.
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.4, # 분량을 넉넉하게 뽑아내기 위해 온도를 살짝 높임
                max_output_tokens=2048
            )
        )
        return response.text.strip()
    except Exception:
        return "대기질 API 연동 지연으로 상세 분석을 생략합니다. 사업장 자체적인 VOCs 누출 점검을 강화해 주시기 바랍니다."
