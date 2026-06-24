import os
import sys
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# 클라우드 DB 모듈 임포트
import supabase_db as database

# .env 파일 로드
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "your_bot_token_here")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "your_chat_id_here")
MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL_SEC", "300"))  # 대시보드 리프레시 안내용

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
        "24H 외부 수집 스레드가 클라우드 DB에 데이터를 누적하고 있습니다."
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
            
            # 레인보우 차트 정보가 있는 경우 뱃지 표시
            rainbow_band = btc_info.get('rainbow_band')
            rainbow_color = btc_info.get('rainbow_color')
            if rainbow_band and rainbow_color:
                st.markdown(
                    f"🌈 **Rainbow Chart**: <span style='background-color: {rainbow_color}; color: #000000; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 0.9em;'>{rainbow_band}</span>",
                    unsafe_allow_html=True
                )
                
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
