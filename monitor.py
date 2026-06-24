import os
import sys
import time
from datetime import datetime
import pandas as pd
import requests
from dotenv import load_dotenv

# Supabase 연동 모듈 임포트
import supabase_db as database

# .env 로드
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL_SEC", "300"))  # 기본 5분(300초)

def fetch_binance_ohlcv(symbol: str, limit: int = 50) -> list:
    """Binance API v3를 호출하여 4시간봉 데이터를 받아옵니다."""
    formatted_symbol = symbol.replace("/", "")
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": formatted_symbol,
        "interval": "4h",
        "limit": limit
    }
    # 연결 타임아웃 5초, 읽기 타임아웃 15초로 설정하여 행(Hang) 현상을 원천 방지합니다.
    response = requests.get(url, params=params, timeout=(5, 15))
    response.raise_for_status()
    data = response.json()
    
    formatted = []
    for item in data:
        formatted.append([
            int(item[0]),          # timestamp (ms)
            float(item[1]),        # open
            float(item[2]),        # high
            float(item[3]),        # low
            float(item[4]),        # close
            float(item[5])         # volume
        ])
    return formatted

def calculate_rsi(prices: pd.Series, period: int = 20) -> pd.Series:
    """Pandas를 활용해 정확한 RSI(20) 지표를 계산합니다."""
    delta = prices.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    
    rs = ema_up / (ema_down + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def send_telegram_message(message: str):
    """텔레그램 알림을 발송합니다."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_bot_token_here":
        print(f"[Telegram Skip] Token not set. Message: {message}", flush=True)
        return
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "your_chat_id_here":
        print(f"[Telegram Skip] Chat ID not set. Message: {message}", flush=True)
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=(5, 10))
        if response.status_code == 200:
            print("[Telegram Success] Alert sent successfully.", flush=True)
        else:
            print(f"[Telegram Error] Status code {response.status_code}: {response.text}", flush=True)
    except Exception as e:
        print(f"[Telegram Exception] Failed to send telegram message: {e}", flush=True)

def monitor_markets():
    """주기적으로 데이터를 수집하고 RSI 지표를 분석하여 DB 적재 및 알림을 전송합니다."""
    symbols = {
        "BTC/USDT": "BTC/USDT",
        "ETH/USDT": "ETH/USDT"
    }
    
    print("[Background Monitor] Engine started. Monitoring markets...", flush=True)
    
    while True:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{current_time}] Starting data collection round...", flush=True)
        
        for display_symbol, fetch_symbol in symbols.items():
            try:
                # 바이낸스 시세 호출
                ohlcv = fetch_binance_ohlcv(fetch_symbol, limit=50)
                if not ohlcv:
                    continue
                
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                df['rsi'] = calculate_rsi(df['close'], period=20)
                
                # 1. 실시간 데이터용 (마지막 미완성 캔들)
                latest_row = df.iloc[-1]
                latest_price = float(latest_row['close'])
                latest_rsi = float(latest_row['rsi'])
                
                # Supabase 실시간 가격/RSI 갱신
                database.update_current_status(display_symbol, latest_price, latest_rsi)
                print(f"[{display_symbol}] Live Price: ${latest_price:,.2f}, Live RSI(20): {latest_rsi:.2f}", flush=True)
                
                # 2. 신호 판별 (이전 마감 완성 캔들)
                closed_row = df.iloc[-2]
                closed_time_str = closed_row['datetime'].strftime("%Y-%m-%d %H:%M:%S")
                closed_price = float(closed_row['close'])
                closed_rsi = float(closed_row['rsi'])
                
                # 중복 알림 방지 체크 후 신호 전송
                if not database.is_alert_already_sent(display_symbol, closed_time_str):
                    action = None
                    if closed_rsi <= 25:
                        action = "BUY"
                    elif closed_rsi >= 70:
                        action = "SELL"
                    
                    if action:
                        msg = (
                            f"⚠️ *[{action}] Trading Signal Alert*\n"
                            f"• 코인: {display_symbol}\n"
                            f"• 캔들 시각: {closed_time_str}\n"
                            f"• 종가: ${closed_price:,.2f}\n"
                            f"• RSI(20): {closed_rsi:.2f}"
                        )
                        send_telegram_message(msg)
                        
                        database.add_signal_log(display_symbol, closed_time_str, closed_price, closed_rsi, action)
                        database.record_sent_alert(display_symbol, closed_time_str)
                        print(f"[{display_symbol} Signal Detected] {action} at {closed_time_str} (Price: {closed_price}, RSI: {closed_rsi:.2f})", flush=True)
                        
            except Exception as e:
                print(f"[Error Monitoring {display_symbol}]: {e}", flush=True)
                
        print(f"Finished round. Sleeping for {MONITOR_INTERVAL} seconds...", flush=True)
        time.sleep(MONITOR_INTERVAL)

if __name__ == "__main__":
    print("=== [24H Worker] Starting Crypto RSI Monitor ===", flush=True)
    database.initialize_db()
    monitor_markets()
