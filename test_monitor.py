import os
import sys
import io

# 윈도우 콘솔 UTF-8 출력 설정
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import supabase_db as database
import app
import pandas as pd

def main():
    print("=== Start Backend Monitoring Test ===")
    
    # DB 초기화
    database.initialize_db()
    print("Database initialized.")
    
    # 코인베이스 데이터 수집 및 RSI 계산 테스트
    symbols = {
        "BTC/USDT": "BTC/USDT",
        "ETH/USDT": "ETH/USDT"
    }
    
    for display_symbol, fetch_symbol in symbols.items():
        try:
            print(f"Fetching data for {display_symbol}...")
            import monitor
            ohlcv = monitor.fetch_kucoin_ohlcv(fetch_symbol, limit=50)
            print(f"Fetched {len(ohlcv)} candles.")
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['rsi'] = monitor.calculate_rsi(df['close'], period=20)
            
            # 실시간 수치 확인
            latest_row = df.iloc[-1]
            latest_price = float(latest_row['close'])
            latest_rsi = float(latest_row['rsi'])
            print(f"[{display_symbol}] Price: {latest_price:,.2f}, RSI(20): {latest_rsi:.2f}")
            
            # DB 업데이트 테스트
            rainbow_band = None
            rainbow_color = None
            if display_symbol == "BTC/USDT":
                rainbow_band, rainbow_color = monitor.fetch_bitcoin_rainbow_chart()
                print(f"[{display_symbol}] Rainbow: {rainbow_band} ({rainbow_color})")
            database.update_current_status(display_symbol, latest_price, latest_rsi, rainbow_band, rainbow_color)
            
            # 가짜 신호 하나 추가해서 로그 테스트
            # 캔들 시각 기준 (RSI가 25 이하인 가짜 신호 생성)
            closed_row = df.iloc[-2]
            closed_time_str = closed_row['datetime'].strftime("%Y-%m-%d %H:%M:%S")
            database.add_signal_log(
                symbol=display_symbol,
                timestamp=closed_time_str,
                price=float(closed_row['close']),
                rsi=22.5, # 25 이하
                action="BUY_TEST"
            )
            print(f"[{display_symbol}] Inserted test signal log.")
            
        except Exception as e:
            print(f"Error fetching/processing {display_symbol}: {e}")
            
    # DB 결과 조회 출력
    print("\n--- DB Current Status ---")
    status = database.get_current_status()
    for row in status:
        print(row)
        
    print("\n--- DB Signal Logs ---")
    logs = database.get_signal_logs(limit=5)
    for log in logs:
        print(log)
        
    # 텔레그램 함수 호출 테스트
    print("\n--- Telegram Send Function Test ---")
    monitor.send_telegram_message("🔔 [Test] Crypto RSI Dashboard backend verification message.")
    
    print("\n=== Test Completed ===")

if __name__ == "__main__":
    main()
