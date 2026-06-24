import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

def get_headers(prefer_upsert=False):
    """Supabase REST API 요청을 위한 기본 헤더를 반환합니다."""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    if prefer_upsert:
        # 중복 시 업데이트(UPSERT) 처리 및 최소 응답 데이터 설정
        headers["Prefer"] = "resolution=merge-duplicates, return=minimal"
    return headers

def update_current_status(symbol: str, price: float, rsi: float):
    """실시간 가격 및 RSI 수치를 Supabase 클라우드 DB에 UPSERT 합니다."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[Supabase Warning] URL or KEY not set. Skipping update_current_status.")
        return
        
    url = f"{SUPABASE_URL}/rest/v1/current_status"
    from datetime import timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    
    payload = {
        "symbol": symbol,
        "price": price,
        "rsi": rsi,
        "last_updated": now_str
    }
    
    try:
        response = requests.post(url, json=payload, headers=get_headers(prefer_upsert=True), timeout=10)
        # 201 Created or 204 No Content(return=minimal 시)
        if response.status_code not in [200, 201, 204]:
            print(f"[Supabase Error] update_current_status failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[Supabase Exception] update_current_status error: {e}")

def get_current_status():
    """Supabase DB에 기록된 최신 가격 및 RSI 상태 목록을 반환합니다."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
        
    url = f"{SUPABASE_URL}/rest/v1/current_status?select=*"
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[Supabase Error] get_current_status failed: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"[Supabase Exception] get_current_status error: {e}")
        return []

def is_alert_already_sent(symbol: str, timestamp: str) -> bool:
    """특정 코인의 특정 캔들 시각에 대해 알림이 이미 전송되었는지 조회합니다."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
        
    # 필터링하여 select
    url = f"{SUPABASE_URL}/rest/v1/sent_alerts?symbol=eq.{symbol}&timestamp=eq.{timestamp}&select=symbol"
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        if response.status_code == 200:
            data = response.json()
            return len(data) > 0
        else:
            print(f"[Supabase Error] is_alert_already_sent query failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[Supabase Exception] is_alert_already_sent error: {e}")
        return False

def record_sent_alert(symbol: str, timestamp: str):
    """알림이 전송되었음을 Supabase DB에 기록합니다."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
        
    url = f"{SUPABASE_URL}/rest/v1/sent_alerts"
    payload = {
        "symbol": symbol,
        "timestamp": timestamp
    }
    
    try:
        # Ignore on conflict
        headers = get_headers()
        headers["Prefer"] = "resolution=ignore, return=minimal"
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code not in [200, 201, 204]:
            print(f"[Supabase Error] record_sent_alert failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[Supabase Exception] record_sent_alert error: {e}")

def add_signal_log(symbol: str, timestamp: str, price: float, rsi: float, action: str):
    """매매 신호 이력을 Supabase DB에 기록합니다."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
        
    url = f"{SUPABASE_URL}/rest/v1/signal_logs"
    from datetime import timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    
    payload = {
        "symbol": symbol,
        "timestamp": timestamp,
        "price": price,
        "rsi": rsi,
        "action": action,
        "created_at": now_str
    }
    
    try:
        headers = get_headers()
        headers["Prefer"] = "return=minimal"
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code not in [200, 201, 204]:
            print(f"[Supabase Error] add_signal_log failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[Supabase Exception] add_signal_log error: {e}")

def get_signal_logs(limit: int = 50):
    """매매 신호 기록을 최신순으로 조회합니다."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
        
    # created_at 내림차순(desc) 정렬 및 limit 조건 적용
    url = f"{SUPABASE_URL}/rest/v1/signal_logs?select=*&order=created_at.desc&limit={limit}"
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[Supabase Error] get_signal_logs failed: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"[Supabase Exception] get_signal_logs error: {e}")
        return []

def initialize_db():
    """클라우드 환경에서는 사용자가 SQL 스크립트로 직접 생성하므로, 호환성 유지를 위해 빈 함수로 둡니다."""
    pass

