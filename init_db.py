import sqlite3
import os
from datetime import datetime

def init_database():
    """데이터베이스 초기화 및 테이블 생성"""
    db_path = 'shipping_plan.db'
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 선적계획 메인 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shipping_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            to_site TEXT NOT NULL,
            model_name TEXT NOT NULL,
            shipping_week TEXT NOT NULL,
            shipping_quantity INTEGER NOT NULL,
            remark TEXT CHECK (LENGTH(remark) <= 100),
            created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            updated_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            is_deleted BOOLEAN DEFAULT FALSE
        )
    ''')
    
    # 히스토리 테이블 (변경 추적)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shipping_plans_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            changed_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (plan_id) REFERENCES shipping_plans (id)
        )
    ''')
    
    # 샘플 데이터 추가
    # cursor.execute('SELECT COUNT(*) FROM shipping_plans')
    # if cursor.fetchone()[0] == 0:
    #     sample_data = [
    #         ('삼성전자', '부산항', 'Galaxy S24', '2024-40주차', 1000),
    #         ('LG전자', '인천항', 'OLED TV 55"', '2024-41주차', 1500),
    #         ('현대자동차', '울산항', 'Sonata', '2024-42주차', 2000),
    #         ('SK하이닉스', '평택항', 'DDR5 메모리', '2024-43주차', 800)
    #     ]
        
    #     cursor.executemany('''
    #         INSERT INTO shipping_plans (company_name, to_site, model_name, shipping_week, shipping_quantity)
    #         VALUES (?, ?, ?, ?, ?)
    #     ''', sample_data)
        
    conn.commit()
    conn.close()
    print("데이터베이스가 초기화되었습니다.")

if __name__ == '__main__':
    init_database()