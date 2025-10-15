import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

def get_db_connection():
    """Supabase PostgreSQL 연결 반환"""
    try:
        conn = psycopg2.connect(
            user=os.getenv("user"),
            password=os.getenv("password"),
            host=os.getenv("host"),
            port=os.getenv("port"),
            database=os.getenv("dbname"),
            sslmode="require",
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

def test_queries():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("=" * 60)
    print("🔍 SHIPPING_PLANS 테이블 CASE문 테스트")
    print("=" * 60)
    
    # 1. 일반 조회 (원본 데이터)
    print("\n1️⃣ 일반 조회 - 원본 데이터")
    print("-" * 40)
    cursor.execute('''
        SELECT from_site, to_site, model_name, shipping_week, 
               shipping_quantity, shipped_quantity, is_finished
        FROM shipping_plans 
        WHERE is_deleted = FALSE
        ORDER BY shipping_week
    ''')
    
    normal_result = cursor.fetchall()
    print(f"총 {len(normal_result)}개 레코드:")
    for i, row in enumerate(normal_result, 1):
        print(f"[{i}] shipping_week: {row['shipping_week']}, "
              f"finished: {row['is_finished']}, "
              f"from: {row['from_site']}, "
              f"quantity: {row['shipping_quantity']}")
    
    # 2. CASE문 적용 조회
    print("\n2️⃣ CASE문 적용 조회")
    print("-" * 40)
    
    # 파라미터 설정
    week_from = "2025-10-13(W42)"
    
    cursor.execute('''
        SELECT from_site, to_site, model_name,
               shipping_week as original_week,
               CASE 
                   WHEN shipping_week < %s AND is_finished = FALSE
                   THEN %s
                   ELSE shipping_week 
               END AS new_week,
               shipping_quantity, shipped_quantity, is_finished
        FROM shipping_plans 
        WHERE is_deleted = FALSE
        ORDER BY shipping_week
    ''', [week_from, week_from])
    
    case_result = cursor.fetchall()
    print(f"총 {len(case_result)}개 레코드:")
    print(f"CASE 조건: shipping_week < '{week_from}' AND is_finished = FALSE")
    print(f"CASE THEN: '{week_from}'")
    print()
    
    for i, row in enumerate(case_result, 1):
        changed = "✅ 변경됨" if row['original_week'] != row['new_week'] else "➖ 그대로"
        print(f"[{i}] 원본: {row['original_week']} → 결과: {row['new_week']} ({changed})")
        print(f"    finished: {row['is_finished']}, quantity: {row['shipping_quantity']}")
        print()
    
    # 3. WHERE 조건까지 포함한 복합 쿼리 테스트
    print("\n3️⃣ 복합 쿼리 (WHERE + CASE) 테스트")
    print("-" * 40)
    
    week_to = "2025-11-10(W46)"
    
    cursor.execute('''
        SELECT from_site, to_site, model_name,
               shipping_week as original_week,
               CASE 
                   WHEN shipping_week < %s AND is_finished = FALSE
                   THEN %s
                   ELSE shipping_week 
               END AS new_week,
               shipping_quantity, shipped_quantity, is_finished
        FROM shipping_plans 
        WHERE is_deleted = FALSE 
          AND ((shipping_week >= %s AND shipping_week <= %s) 
               OR (shipping_week < %s AND is_finished = FALSE))
        ORDER BY shipping_week
    ''', [week_from, week_from, week_from, week_to, week_from])
    
    complex_result = cursor.fetchall()
    print(f"총 {len(complex_result)}개 레코드:")
    print(f"WHERE 조건1: shipping_week >= '{week_from}' AND shipping_week <= '{week_to}'")
    print(f"WHERE 조건2: shipping_week < '{week_from}' AND is_finished = FALSE")
    print(f"CASE 조건: shipping_week < '{week_from}' AND is_finished = FALSE")
    print(f"CASE THEN: '{week_from}'")
    print()
    
    for i, row in enumerate(complex_result, 1):
        changed = "✅ 변경됨" if row['original_week'] != row['new_week'] else "➖ 그대로"
        print(f"[{i}] 원본: {row['original_week']} → 결과: {row['new_week']} ({changed})")
        print(f"    finished: {row['is_finished']}, quantity: {row['shipping_quantity']}")
        print()
    
    # 4. 파라미터 순서 확인 테스트
    print("\n4️⃣ 파라미터 순서 확인 테스트")
    print("-" * 40)
    
    cursor.execute('''
        SELECT shipping_week as original_week,
               CASE 
                   WHEN shipping_week < %s AND is_finished = FALSE
                   THEN %s
                   ELSE shipping_week 
               END AS new_week,
               is_finished
        FROM shipping_plans 
        WHERE is_deleted = FALSE
        ORDER BY shipping_week
    ''', ["2025-10-13(W42)", "PARAM_TEST"])  # 두 번째 파라미터를 특별한 값으로
    
    param_test = cursor.fetchall()
    print("파라미터 테스트 - CASE THEN에 'PARAM_TEST' 넣음:")
    for row in param_test:
        if row['new_week'] == 'PARAM_TEST':
            print(f"✅ 원본: {row['original_week']} → PARAM_TEST (CASE 적용됨)")
        else:
            print(f"➖ 원본: {row['original_week']} → {row['new_week']} (CASE 미적용)")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    test_queries()