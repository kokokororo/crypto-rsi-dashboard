import os
import sys
import io
import time
import threading
from datetime import datetime
import streamlit as st
import pandas as pd
import requests
from dotenv import load_dotenv

# 클라우드 DB 모듈 임포트
import supabase_db as database

# .env 파일 로드
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "your_bot_token_here")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "your_chat_id_here")
MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL_SEC", "300"))  # 기본 5분(300초)

def fetch_bybit_ohlcv(symbol: str, limit: int = 50) -> list:
    """Bybit API v5를 직접 호출하여 4시간봉 데이터를 받아옵니다.
    반환 형식: [[timestamp_ms, open, high, low, close, volume], ...] (과거 -> 최신 순)
    """
    url = "https://api.bybit.com/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": "240",  # 4시간봉 (240분)
        "limit": limit
    }
    
    # 한국 IP 환경 등에서 Bybit API 응답 지연이 있을 수 있으므로 타임아웃 15초 설정
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    
    if data.get("retCode") != 0:
        raise Exception(f"Bybit API Error ({data.get('retCode')}): {data.get('retMsg')}")
        
    raw_list = data["result"]["list"]
    
    # Bybit API v5 kline list는 최신 데이터가 index 0에 위치하므로
    # 시간 순서대로 정렬하기 위해 리스트를 역순(과거->최신)으로 뒤집습니다.
    raw_list.reverse()
    
    formatted = []
    for item in raw_list:
        # item: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
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
    
    # Exponential Moving Average를 통한 Wilder's Smoothing 적용
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    
    rs = ema_up / (ema_down + 1e-10)  # 0 나누기 방지
    rsi = 100 - (100 / (1 + rs))
    return rsi

def send_telegram_message(message: str):
    """텔레그램 알림을 발송합니다. 설정이 유효하지 않으면 콘솔에 로그만 남깁니다."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_bot_token_here":
        print(f"[Telegram Skip] Token not set. Message: {message}")
        return
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "your_chat_id_here":
        print(f"[Telegram Skip] Chat ID not set. Message: {message}")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("[Telegram Success] Alert sent successfully.")
        else:
            print(f"[Telegram Error] Status code {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[Telegram Exception] Failed to send telegram message: {e}")

def monitor_markets():
    """백그라운드에서 동작하며 주기적으로 데이터를 수집하고 RSI 지표를 분석합니다."""
    # API 요청을 위한 Bybit 심볼 매핑
    symbols = {
        "BTC/USDT": "BTCUSDT",
        "ETH/USDT": "ETHUSDT"
    }
    
    print("[Background Monitor] Thread started (Using Bybit API v5).")
    
    while True:
        for display_symbol, fetch_symbol in symbols.items():
            try:
                # Bybit API v5 직접 호출
                ohlcv = fetch_bybit_ohlcv(fetch_symbol, limit=50)
                if not ohlcv:
                    continue
                
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                # 타임스탬프를 datetime 객체(KST 등 읽기 편한 형태)로 변환
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                # RSI 계산
                df['rsi'] = calculate_rsi(df['close'], period=20)
                
                # 1. 실시간 데이터용 (가장 최근인 마지막 행 - 미완성 캔들)
                latest_row = df.iloc[-1]
                latest_price = float(latest_row['close'])
                latest_rsi = float(latest_row['rsi'])
                
                # 실시간 정보 DB 업데이트
                database.update_current_status(display_symbol, latest_price, latest_rsi)
                
                # 2. 신호 판별 및 중복 방지 (바로 이전 마감된 완성 캔들 index -2 기준)
                closed_row = df.iloc[-2]
                closed_time_str = closed_row['datetime'].strftime("%Y-%m-%d %H:%M:%S")
                closed_price = float(closed_row['close'])
                closed_rsi = float(closed_row['rsi'])
                
                # 중복 알림 방지 체크
                if not database.is_alert_already_sent(display_symbol, closed_time_str):
                    action = None
                    # 기본 샘플 신호 조건 (RSI <= 25: BUY, RSI >= 70: SELL)
                    if closed_rsi <= 25:
                        action = "BUY"
                    elif closed_rsi >= 70:
                        action = "SELL"
                    
                    if action:
                        # 알림 전송 및 기록
                        msg = (
                            f"⚠️ *[{action}] Trading Signal Alert*\n"
                            f"• 코인: {display_symbol}\n"
                            f"• 캔들 시각: {closed_time_str}\n"
                            f"• 종가: ${closed_price:,.2f}\n"
                            f"• RSI(20): {closed_rsi:.2f}"
                        )
                        send_telegram_message(msg)
                        
                        # DB에 기록
                        database.add_signal_log(display_symbol, closed_time_str, closed_price, closed_rsi, action)
                        database.record_sent_alert(display_symbol, closed_time_str)
                        print(f"[Signal Detected] {display_symbol} {action} at {closed_time_str} (Price: {closed_price}, RSI: {closed_rsi:.2f})")
                        
            except Exception as e:
                print(f"[Error Monitoring {display_symbol}]: {e}")
                
        time.sleep(MONITOR_INTERVAL)

# Streamlit 버전 호환 캐싱 데코레이터 선택
if hasattr(st, "cache_resource"):
    # 최신 Streamlit 버전 (Streamlit Cloud 등)
    cache_decorator = st.cache_resource
elif hasattr(st, "experimental_singleton"):
    # 구형 Streamlit 버전 (로컬 32비트 환경 등)
    cache_decorator = st.experimental_singleton
else:
    # 폴백
    cache_decorator = lambda f: f

# 백그라운드 모니터링 스레드 캐싱 및 실행
@cache_decorator
def start_monitor_thread():
    database.initialize_db()
    thread = threading.Thread(target=monitor_markets, daemon=True)
    thread.start()
    return thread

def render_signal_logs_as_html(logs) -> str:
    """RSI 매매 신호 이력을 모던한 스타일의 HTML 테이블로 포맷팅합니다.
    pyarrow 의존성을 완전히 우회하고 더 보기 좋은 테이블 디자인을 제공합니다.
    """
    if not logs:
        return "<p style='color: gray; text-align: center; padding: 20px;'>현재까지 발생한 매매 신호 로그가 없습니다.</p>"
        
    html = """
    <div style="overflow-x: auto;">
        <table style="width: 100%; border-collapse: collapse; margin: 10px 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-width: 500px; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
            <thead>
                <tr style="background-color: #1e1e24; color: #ffffff; text-align: left; font-weight: bold; border-bottom: 2px solid #2d2d34;">
                    <th style="padding: 14px 18px;">코인</th>
                    <th style="padding: 14px 18px;">신호 구분</th>
                    <th style="padding: 14px 18px;">감지 가격</th>
                    <th style="padding: 14px 18px;">감지 RSI</th>
                    <th style="padding: 14px 18px;">캔들 시각</th>
                    <th style="padding: 14px 18px;">알림 전송 시각</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for row in logs:
        action = row['action']
        # BUY: 녹색, SELL: 적색, 기본값: 회색
        if "BUY" in action:
            bg_color = "rgba(40, 167, 69, 0.15)"
            text_color = "#28a745"
            border_color = "rgba(40, 167, 69, 0.3)"
        elif "SELL" in action:
            bg_color = "rgba(220, 53, 69, 0.15)"
            text_color = "#dc3545"
            border_color = "rgba(220, 53, 69, 0.3)"
        else:
            bg_color = "rgba(108, 117, 125, 0.15)"
            text_color = "#6c757d"
            border_color = "rgba(108, 117, 125, 0.3)"
            
        action_badge = (
            f"<span style='background-color: {bg_color}; color: {text_color}; "
            f"border: 1px solid {border_color}; padding: 4px 10px; border-radius: 12px; "
            f"font-size: 0.85em; font-weight: 600; display: inline-block;'>{action}</span>"
        )
        
        html += f"""
                <tr style="border-bottom: 1px solid #f0f0f5; background-color: #ffffff;">
                    <td style="padding: 14px 18px; font-weight: 600; color: #1a1a1a;">{row['symbol']}</td>
                    <td style="padding: 14px 18px;">{action_badge}</td>
                    <td style="padding: 14px 18px; font-weight: bold; color: #2a2a2a;">${row['price']:,.2f}</td>
                    <td style="padding: 14px 18px; font-weight: bold; color: #0056b3;">{row['rsi']:.2f}</td>
                    <td style="padding: 14px 18px; color: #4b5563; font-size: 0.9em;">{row['timestamp']}</td>
                    <td style="padding: 14px 18px; color: #6b7280; font-size: 0.9em;">{row['created_at']}</td>
                </tr>
        """
        
    html += """
            </tbody>
        </table>
    </div>
    """
    return html

# 대시보드 화면 구성
def main():
    st.set_page_config(
        page_title="Crypto RSI Trading Dashboard",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # 백그라운드 엔진 기동
    start_monitor_thread()
    
    # 제목 및 리프레시 영역
    st.title("📈 Crypto RSI 실시간 트레이딩 대시보드")
    st.caption("비트코인(BTC/USDT) 및 이더리움(ETH/USDT)의 4시간봉 RSI(20) 수치를 모니터링합니다.")
    
    # 텔레그램 설정 경고/안내 메시지
    st.sidebar.header("⚙️ 시스템 설정 상태")
    if TELEGRAM_BOT_TOKEN == "your_bot_token_here" or TELEGRAM_CHAT_ID == "your_chat_id_here":
        st.sidebar.warning(
            "⚠️ 텔레그램 설정 미완료\n\n"
            "`.env` 파일에 봇 토큰과 Chat ID를 설정해야 알림이 발송됩니다."
        )
    else:
        st.sidebar.success("✅ 텔레그램 알림 활성화됨")
        
    st.sidebar.info(
        f"⏱️ **모니터링 주기**: {MONITOR_INTERVAL}초\n"
        "백그라운드 스레드가 지속적으로 작동하며 신호를 분석 중입니다."
    )
    
    if st.sidebar.button("🔄 화면 동기화 및 새로고침"):
        st.experimental_rerun()

    # 실시간 모니터링 현황 (Metrics)
    st.subheader("📊 실시간 모니터링 (4시간봉 기준)")
    
    # DB에서 최신 데이터 조회
    current_status = database.get_current_status()
    
    # 2열 메트릭 카드 배치
    col1, col2 = st.columns(2)
    
    status_map = {row['symbol']: row for row in current_status}
    
    # BTC 카드
    with col1:
        st.subheader("Bitcoin (BTC/USDT)")
        btc_info = status_map.get("BTC/USDT")
        if btc_info:
            rsi_val = btc_info['rsi']
            price_val = btc_info['price']
            
            # RSI 수치에 따른 데코레이션
            rsi_delta = ""
            if rsi_val <= 25:
                rsi_delta = "과매도 영역 진입 (BUY 권장)"
            elif rsi_val >= 70:
                rsi_delta = "과매수 영역 진입 (SELL 권장)"
                
            st.metric(label="현재 시세", value=f"${price_val:,.2f}")
            st.metric(label="현재 RSI(20)", value=f"{rsi_val:.2f}", delta=rsi_delta)
            st.caption(f"마지막 업데이트: {btc_info['last_updated']}")
        else:
            st.info("데이터를 수집하고 있습니다. 잠시만 기다려 주세요...")
            
    # ETH 카드
    with col2:
        st.subheader("Ethereum (ETH/USDT)")
        eth_info = status_map.get("ETH/USDT")
        if eth_info:
            rsi_val = eth_info['rsi']
            price_val = eth_info['price']
            
            rsi_delta = ""
            if rsi_val <= 25:
                rsi_delta = "과매도 영역 진입 (BUY 권장)"
            elif rsi_val >= 70:
                rsi_delta = "과매수 영역 진입 (SELL 권장)"
                
            st.metric(label="현재 시세", value=f"${price_val:,.2f}")
            st.metric(label="현재 RSI(20)", value=f"{rsi_val:.2f}", delta=rsi_delta)
            st.caption(f"마지막 업데이트: {eth_info['last_updated']}")
        else:
            st.info("데이터를 수집하고 있습니다. 잠시만 기다려 주세요...")

    st.markdown("---")
    
    # 신호 로그 테이블
    st.subheader("📜 매매 신호 이력 (Signal Logs)")
    logs = database.get_signal_logs(limit=30)
    
    # HTML 포맷팅 테이블 적용
    html_table = render_signal_logs_as_html(logs)
    st.markdown(html_table, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
