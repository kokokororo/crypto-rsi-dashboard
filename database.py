import sqlite3
from datetime import datetime

DB_FILE = "trading.db"

def get_connection():
    return sqlite3.connect(DB_FILE)

def initialize_db():
    """데이터베이스 테이블을 초기화합니다."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 실시간 시세 및 RSI 최신 상태 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS current_status (
                symbol TEXT PRIMARY KEY,
                price REAL,
                rsi REAL,
                last_updated TEXT
            )
        """)
        
        # 신호 로그 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                timestamp TEXT,
                price REAL,
                rsi REAL,
                action TEXT,
                created_at TEXT
            )
        """)
        
        # 알림이 전송된 캔들 타임스탬프 기록 테이블 (중복 알림 방지)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sent_alerts (
                symbol TEXT,
                timestamp TEXT,
                PRIMARY KEY (symbol, timestamp)
            )
        """)
        
        conn.commit()

def update_current_status(symbol: str, price: float, rsi: float):
    """현재 가격과 RSI 상태를 업데이트합니다."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO current_status (symbol, price, rsi, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                price=excluded.price,
                rsi=excluded.rsi,
                last_updated=excluded.last_updated
        """, (symbol, price, rsi, now_str))
        conn.commit()

def get_current_status():
    """최신 가격 및 RSI 상태를 모두 조회합니다."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM current_status")
        return [dict(row) for row in cursor.fetchall()]

def is_alert_already_sent(symbol: str, timestamp: str) -> bool:
    """해당 코인의 특정 캔들 타임스탬프에 대한 알림이 이미 전송되었는지 확인합니다."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM sent_alerts WHERE symbol = ? AND timestamp = ?
        """, (symbol, timestamp))
        return cursor.fetchone() is not None

def record_sent_alert(symbol: str, timestamp: str):
    """알림이 전송되었음을 기록합니다."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO sent_alerts (symbol, timestamp) VALUES (?, ?)
        """, (symbol, timestamp))
        conn.commit()

def add_signal_log(symbol: str, timestamp: str, price: float, rsi: float, action: str):
    """발생한 매매 신호를 로그로 기록합니다."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signal_logs (symbol, timestamp, price, rsi, action, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (symbol, timestamp, price, rsi, action, now_str))
        conn.commit()

def get_signal_logs(limit: int = 50):
    """신호 로그를 최신순으로 조회합니다."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM signal_logs ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
