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
            email TEXT UNIQUE,
            avatar TEXT,
            approved INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            last_login TIMESTAMPTZ DEFAULT NOW()
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
            type TEXT NOT NULL,
            is_terminated BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        ''')
        print("companies table created successfully")

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
            cursor.execute('INSERT INTO companies (name, type, is_terminated) VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING', (name, ctype, False))
        
        print("Companies data inserted successfully")

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
        
        # 통합 히스토리(감사) 테이블 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_history (
            id SERIAL PRIMARY KEY,
            table_name TEXT NOT NULL,
            record_id TEXT NOT NULL,
            action TEXT NOT NULL, -- 'INSERT', 'UPDATE', 'DELETE'
            field_name TEXT,      -- 전체 row 기록시 NULL
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT,
            changed_at TIMESTAMPTZ DEFAULT NOW()
            )
            ''')
        print("audit_history table created successfully")

        # Booking Requests Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS booking_requests (
            id SERIAL PRIMARY KEY,
            booking_request_number VARCHAR(32) UNIQUE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            created_by INTEGER NOT NULL REFERENCES users(id),
            shipper TEXT,
            shipping_week TEXT,
            to_site TEXT,
            final_destination TEXT,
            consignee TEXT,
            notify TEXT,
            crd DATE,
            pol TEXT,
            transport_mode TEXT,
            logistics_contact_id INTEGER REFERENCES users(id),
            remark TEXT,
            status TEXT,
            -- 예약 확정 정보
            so_number TEXT,
            pod TEXT,
            shipping_liner TEXT,
            vessel_name TEXT,
            voyage TEXT,
            cy_open_time TIMESTAMPTZ,
            si_cut_time TIMESTAMPTZ,
            cy_cls_time TIMESTAMPTZ,
            etd DATE,
            eta DATE,
            hbl TEXT,
            schedule_remark TEXT,
            on_board_date DATE
            )
            ''')
        print("booking_requests table created successfully")

        # Booking Containers Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS booking_containers (
            id SERIAL PRIMARY KEY,
            booking_request_id INTEGER NOT NULL REFERENCES booking_requests(id),
            container_type TEXT
        )
        ''')
        print("booking_containers table created successfully")

        # Booking Items Table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS booking_items (
            id SERIAL PRIMARY KEY,
            container_id INTEGER NOT NULL REFERENCES booking_containers(id),
            model TEXT,
            qty INTEGER
        )
        ''')
        print("booking_items table created successfully")


        # 변경사항 커밋 - 이것이 없으면 테이블이 실제로 생성되지 않습니다!
        conn.commit()
        print("Database initialization completed successfully!")
        return True

    except Exception as e:
        print(f"Error initializing database: {e}")
        if conn:
            conn.rollback()
        return False
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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