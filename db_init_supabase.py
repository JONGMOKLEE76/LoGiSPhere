import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os
from datetime import datetime

# Load environment variables
load_dotenv()

def get_connection():
    """Supabase PostgreSQL 연결 반환"""
    try:
        connection = psycopg2.connect(
            user=os.getenv("user"),
            password=os.getenv("password"),
            host=os.getenv("host"),
            port=os.getenv("port"),
            database=os.getenv("dbname"),
            sslmode="require"
        )
        return connection
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

def init_database():
    """Supabase PostgreSQL 데이터베이스 초기화"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # shipment_plan 테이블 생성 (SQLite AUTOINCREMENT -> PostgreSQL SERIAL)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS shipment_plan (
            id SERIAL PRIMARY KEY,
            from_site TEXT,
            to_site TEXT,
            mapping_model_suffix TEXT,
            week_name TEXT,
            ship_qty INTEGER,
            po_no TEXT,
            po_qty INTEGER,
            created_by TEXT,
            created_at TIMESTAMP,
            remark TEXT
        )
        ''')
        print("shipment_plan table created successfully")

        # users 테이블 생성 
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            company TEXT,
            job TEXT,
            email TEXT,
            avatar TEXT,
            approved INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP,
            last_login TIMESTAMP
        )
        ''')
        print("users table created successfully")

        # companies 테이블 생성
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL
        )
        ''')
        print("companies table created successfully")

        # 관리자 계정 추가 (이미 있으면 추가하지 않음)
        cursor.execute('SELECT * FROM users WHERE username = %s', ('admin',))
        admin = cursor.fetchone()
        
        if not admin:
            cursor.execute('''
            INSERT INTO users (username, password, company, job, email, avatar, approved, is_admin, created_at) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', ('admin', 'admin123', 'LG Electronics', 'Administrator', 'admin@example.com', 'avatar1.png', 1, 1, datetime.now()))
            print('Admin user created.')
        else:
            print('Admin user already exists.')

        # 회사 목록 추가
        company_list = [
            ('AUO', 'Outsourcing'),
            ('BOEVT', 'Outsourcing'),
            ('KTC', 'Outsourcing'),
            ('MOKA', 'Outsourcing'),
            ('TPV', 'Outsourcing'),
            ('LGE', 'LG Electronics'),
            ('Pantos', 'Logistics'),
            ('UNICO', 'Logistics')
        ]

        for name, ctype in company_list:
            cursor.execute('INSERT INTO companies (name, type) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING', (name, ctype))
        
        print("Companies data inserted successfully")

        # 변경사항 커밋
        conn.commit()
        print("Database initialization completed successfully!")
        return True

    except Exception as e:
        print(f"Database initialization failed: {e}")
        conn.rollback()
        return False
    
    finally:
        cursor.close()
        conn.close()

def test_connection():
    """데이터베이스 연결 테스트"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT NOW();")
        result = cursor.fetchone()
        print(f"Connection test successful. Current time: {result[0]}")
        return True
    
    except Exception as e:
        print(f"Connection test failed: {e}")
        return False
    
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("Starting Supabase database initialization...")
    
    # 연결 테스트
    if test_connection():
        # 데이터베이스 초기화
        init_database()
    else:
        print("Cannot proceed without database connection.")