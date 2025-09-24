import sqlite3
import os
from datetime import datetime

def create_po_table():
    """PO 테이블 생성"""
    db_path = 'shipping_plan.db'
    
    # 데이터베이스 파일이 없으면 먼저 생성 필요
    if not os.path.exists(db_path):
        print("Error: shipping_plan.db 파일이 존재하지 않습니다. 먼저 init_db.py를 실행해주세요.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # PO 정보 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number TEXT NOT NULL UNIQUE,
            from_site TEXT NOT NULL,
            to_site TEXT NOT NULL,
            model TEXT NOT NULL,
            po_qty INTEGER NOT NULL,
            rsd DATE NOT NULL CHECK (rsd IS date(rsd)),
            remark TEXT CHECK (LENGTH(remark) <= 100),
            created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            last_update TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            status TEXT DEFAULT 'Active'
        )
    ''')
    
    # PO 히스토리 테이블 (변경 추적)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchase_orders_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_id INTEGER NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            changed_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (po_id) REFERENCES purchase_orders (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("PO 테이블이 성공적으로 생성되었습니다.")
    print("생성된 테이블:")
    print("- purchase_orders: PO 정보")
    print("- purchase_orders_history: PO 변경 히스토리")

if __name__ == '__main__':
    create_po_table()