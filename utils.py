import requests
from urllib.parse import unquote

# 공공데이터 API 호출 (Double Encoding 방지)
def get_air_quality(station_name: str, api_key: str):
    if not api_key or not station_name: return None
    
    # URL에 직접 키를 결합하여 인코딩 충돌 방지
    url = f"http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty?serviceKey={api_key}"
    params = {
        "returnType": "json", 
        "numOfRows": "1", 
        "pageNo": "1", 
        "stationName": station_name, 
        "dataTerm": "DAILY", 
        "ver": "1.0"
    }
    
    try:
        resp = requests.get(url, params=params, timeout=8)
        data = resp.json()
        items = data.get("response", {}).get("body", {}).get("items", [])
        return items[0] if items else None
    except:
        return None

def get_auto_station_and_coord(address: str):
    STATION_MAPPING = {"홍성": "내포", "예산": "내포", "대전": "성남동", "천안": "성황동"}
    for k, v in STATION_MAPPING.items():
        if k in address: return v, (0.5, 0.5)
    return "내포", (0.5, 0.5)

def get_env_office(address: str):
    if "충남" in address: return "금강유역환경청"
    return "관할 환경청 확인필요"

def get_limit_ppm(industry: str):
    if "III" in industry: return "100ppm"
    return "50ppm"

def generate_rich_advice(air_data: dict, target_station: str):
    o3 = air_data.get('o3Value', '0.055') if air_data else '0.055'
    return f"[상태 알림] 현재 {target_station} 측정소 오존 농도는 {o3}ppm 입니다.\n환경 관리 기준을 준수하시기 바랍니다."
