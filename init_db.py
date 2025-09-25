import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os

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
            created_at TIMESTAMPTZ DEFAULT NOW(),
            last_login TIMESTAMPTZ
        )
        ''')
        print("users table created successfully")

        # 관리자 계정 추가 (이미 있으면 추가하지 않음)
        cursor.execute('SELECT * FROM users WHERE is_admin = %s', (1,))
        admin = cursor.fetchone()
        
        if not admin:
            cursor.execute('''
            INSERT INTO users (username, password, company, job, email, avatar, approved, is_admin) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', ('Paul Lee', 'a43ko0', 'LGE', 'Administrator', 'paul76.lee@lge.com', 'avatar1.png', 1, 1))
            print('Admin user created.')
        else:
            print('Admin user already exists.')


        # companies 테이블 생성
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL
        )
        ''')
        print("companies table created successfully")

        # 선적계획 메인 테이블
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS shipping_plans (
            id SERIAL PRIMARY KEY,
            from_site TEXT NOT NULL,
            to_site TEXT NOT NULL,
            model_name TEXT NOT NULL,
            shipping_week TEXT NOT NULL,
            shipping_quantity INTEGER NOT NULL,
            remark TEXT CHECK (LENGTH(remark) <= 100),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            is_deleted BOOLEAN DEFAULT FALSE
        )
        ''')
        print("shipping_plans table created successfully")

        # 선적 계획 히스토리 테이블 (변경 추적)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS shipping_plans_history (
                history_id SERIAL PRIMARY KEY,
                plan_id INTEGER NOT NULL,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                changed_at TIMESTAMPTZ DEFAULT NOW(),
                FOREIGN KEY (plan_id) REFERENCES shipping_plans (id)
            )
        ''')
        print("shipping_plans_history table created successfully")

        # PO 정보 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id SERIAL PRIMARY KEY,
                po_number TEXT NOT NULL UNIQUE,
                from_site TEXT NOT NULL,
                to_site TEXT NOT NULL,
                model TEXT NOT NULL,
                po_qty INTEGER NOT NULL,
                rsd DATE NOT NULL,
                remark TEXT CHECK (LENGTH(remark) <= 100),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                last_update TIMESTAMPTZ DEFAULT NOW(),
                status TEXT DEFAULT 'Active'
            )
        ''')
        print("purchase_orders table created successfully")
        
        # PO 히스토리 테이블 (변경 추적)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS purchase_orders_history (
                history_id SERIAL PRIMARY KEY,
                po_id INTEGER NOT NULL,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                changed_at TIMESTAMPTZ DEFAULT NOW(),
                FOREIGN KEY (po_id) REFERENCES purchase_orders (id)
            )
        ''')
        print("purchase_orders_history table created successfully")

    except Exception as e:
        print(f"Error initializing database: {e}")
        return False
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    
    print("Database initialized successfully.")

def test_connection():
    """데이터베이스 연결 테스트"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # 서버 UTC 시간
        cursor.execute("SELECT NOW();")
        utc_time = cursor.fetchone()[0]
        
        # 한국시간으로 변환
        cursor.execute("SELECT NOW() AT TIME ZONE 'Asia/Seoul';")
        korea_time = cursor.fetchone()[0]
        
        print(f"Connection test successful!")
        print(f"Server UTC time: {utc_time}")
        print(f"Korea time: {korea_time}")
        return True
    
    except Exception as e:
        print(f"Connection test failed: {e}")
        return False
    
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    print("Starting Supabase database initialization...")

    # 연결 테스트
    if test_connection():
        # 데이터베이스 초기화
        init_database()
    else:
        print("Cannot proceed without database connection.")