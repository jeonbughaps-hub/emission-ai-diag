import requests
from urllib.parse import unquote

FONT_FILE_NAME  = "NanumGothic-Regular.ttf"
FONT_BOLD_NAME  = "NanumGothic-Bold.ttf"

BRAND_NAVY      = (68,  100, 148)   
BRAND_ACCENT    = (91,  155, 213)   
BRAND_ORANGE    = (220, 110,  80)   
BRAND_LIGHT_BG  = (242, 247, 252)   
BRAND_HEADER_BG = (215, 229, 245)   

SCORE_COLORS = {
    "A": ( 82, 180, 120),  
    "B": ( 91, 155, 213),  
    "C": (215, 185,  68),  
    "D": (225, 140,  80),  
    "F": (200,  90,  90),  
}

def get_air_status_pm10(val):
    try: v = float(val)
    except (ValueError, TypeError): return "-", (160, 160, 160)
    if v <= 30: return "좋음",    SCORE_COLORS["A"]
    elif v <= 80: return "보통",    SCORE_COLORS["B"]
    elif v <= 150: return "나쁨",    SCORE_COLORS["D"]
    else: return "매우나쁨", SCORE_COLORS["F"]

def get_air_status_pm25(val):
    try: v = float(val)
    except (ValueError, TypeError): return "-", (160, 160, 160)
    if v <= 15: return "좋음",    SCORE_COLORS["A"]
    elif v <= 35: return "보통",    SCORE_COLORS["B"]
    elif v <= 75: return "나쁨",    SCORE_COLORS["D"]
    else: return "매우나쁨", SCORE_COLORS["F"]

def get_air_status_o3(val):
    try: v = float(val)
    except (ValueError, TypeError): return "-", (160, 160, 160)
    if v <= 0.03: return "좋음",    SCORE_COLORS["A"]
    elif v <= 0.09: return "보통",    SCORE_COLORS["B"]
    elif v <= 0.15: return "나쁨",    SCORE_COLORS["D"]
    else: return "매우나쁨", SCORE_COLORS["F"]

def get_env_office(address: str) -> str:
    if not address: return "-"
    ENV_OFFICE_MAP = {
        "충남": "금강유역환경청",  "세종": "금강유역환경청", "대전": "금강유역환경청",  "충북": "금강유역환경청", "전북": "전북지방환경청", "전주": "전북지방환경청",
        "광주": "영산강유역환경청", "전남": "영산강유역환경청", "제주": "영산강유역환경청",
        "경북": "대구지방환경청", "대구": "대구지방환경청",
        "경남": "낙동강유역환경청", "부산": "낙동강유역환경청", "울산": "낙동강유역환경청",
        "강원": "원주지방환경청",
        "경기": "한강유역환경청",   "서울": "한강유역환경청", "인천": "한강유역환경청",
    }
    for keyword, office in ENV_OFFICE_MAP.items():
        if keyword in address: return office
    return "관할 환경청 확인필요"

def get_auto_station_and_coord(address: str):
    if not address: return "내포", (0.5, 0.5)
    STATION_MAPPING = {
        "전주": "팔복동", "군산": "소룡동", "익산": "남중동", "전북": "팔복동",
        "홍성": "내포", "예산": "내포", "서산": "동문동", "대산": "대산리",
        "당진": "당진시청", "천안": "성황동", "아산": "모종동", "논산": "취암동", "청주": "용암동",
        "여수": "여천동", "순천": "연향동", "광양": "중동", "목포": "용당동"
    }
    for keyword, station_name in STATION_MAPPING.items():
        if keyword in address: return station_name, (0.5, 0.5)
    return "내포", (0.5, 0.5)

def get_limit_ppm(industry: str) -> str:
    if "Ⅰ" in industry or "1" in industry or "I" in industry: return "50ppm"
    if "Ⅱ" in industry or "2" in industry or "II" in industry: return "80ppm"
    if "Ⅲ" in industry or "3" in industry or "III" in industry: return "100ppm"
    return "법적 기준"

def get_air_quality(station_name: str, api_key: str):
    if not api_key or not station_name: return None
    
    # ★ 이중 인코딩 방지를 위해 파라미터를 requests에 안전하게 분리
    url = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
    params = {
        "serviceKey": unquote(api_key), 
        "returnType": "json", 
        "numOfRows": "1", 
        "pageNo": "1", 
        "stationName": station_name, 
        "dataTerm": "DAILY", 
        "ver": "1.0"
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        items = resp.json().get("response", {}).get("body", {}).get("items", [])
        if items and items[0].get("pm10Value") != "-": 
            return items[0]
    except Exception as e: 
        print("API 통신 에러:", e)
        pass
    
    # 실패 시 순수하게 None을 반환하여 빈칸('-') 처리
    return None

def generate_rich_advice(air_data: dict, target_station: str) -> str:
    def _f(v):
        try: return float(v) if v and str(v).replace(".", "").isdigit() else 0.0
        except Exception: return 0.0

    if not air_data:
        return "대기질 정보를 불러오지 못해 관리 지침을 생성할 수 없습니다."

    pm10 = _f(air_data.get("pm10Value", 0))
    o3   = _f(air_data.get("o3Value", 0))

    if o3 >= 0.09:
        level = "[경보 단계 - 즉각 조치 및 비상 가동 가이드]"
        p1 = f"1. 현황 및 리스크 분석 : 사업장 관할 지역({target_station})의 실시간 오존 농도가 {o3:.3f}ppm으로 경보 발령 수준입니다."
        p2 = "2. 현장 즉각 조치 : 옥외 하역, 이송, 코팅 등 비산 누출 위험 공정은 가동을 즉시 중단하고 불가피한 작업은 야간으로 재조정하십시오."
        p3 = "3. 방지시설 긴급 점검 : 대기오염 방지시설의 처리 효율 저하를 막기 위해 차압계 수치를 점검하십시오."
    elif o3 >= 0.04:
        level = "[주의 단계 - 선제적 오염물질 감축 및 관리 권고]"
        p1 = f"1. 대기질 현황 및 잠재적 리스크 : 현재 대기질(오존 {o3:.3f}ppm)은 관리 기준치에 근접하고 있습니다."
        p2 = "2. 선제적 공정 운영 권고 : 오후 피크 시간대에는 유기용제를 다량 사용하는 공정의 가동률을 선제적으로 감축 운영하십시오."
        p3 = "3. 자율 누출 점검(LDAR) 강화 : 회전·연결기기에 대해 수시 누출 점검을 실시하십시오."
    else:
        level = "[정상 단계 - 상시 환경 관리 및 예방적 유지보수 지침]"
        p1 = f"1. 대기질 현황 : 지역 대기질(오존 {o3:.3f}ppm)은 쾌적한 상태를 유지하고 있습니다."
        p2 = "2. 예방적 유지보수 : 방지시설의 처리 효율이 항상 90% 이상 유지될 수 있도록 소모품 교체 주기를 파악하십시오."
        p3 = "3. 현장 기본 수칙 : 유기용제 보관 용기는 사용 직후 밀폐 덮개를 체결하여 원천 차단하십시오."
    return f"{level}\n{p1}\n\n{p2}\n\n{p3}"
