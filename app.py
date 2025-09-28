import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import re
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import sqlite3
from datetime import datetime, timedelta
import os
from collections import defaultdict

# Load environment variables
load_dotenv()   

app = Flask(__name__)
app.secret_key = 'b7f2e8c1-4a2d-4e9a-9c3e-8f1d2a7b6c5e'  # 안전한 랜덤 문자열

# /add_booking 엔드포인트 (1단계: 뼈대만, 실제 저장 로직 없음)
@app.route('/add_booking', methods=['POST'])
def add_booking():
    try:
        data = request.get_json()
        # 2단계: 데이터 유효성 검사
        if not data:
            return jsonify({"success": False, "message": "No data received"}), 400

        # 필수 필드 체크
        required_basic = [
            'shipper', 'shipping_week', 'to_site', 'final_destination',
            'consignee', 'notify', 'crd', 'pol', 'transport_mode'
        ]
        basic = data.get('basic', {})
        missing_basic = [field for field in required_basic if not basic.get(field)]
        if missing_basic:
            return jsonify({"success": False, "message": f"Missing basic fields: {', '.join(missing_basic)}"}), 400

        containers = data.get('containers', [])
        if not containers or not isinstance(containers, list):
            return jsonify({"success": False, "message": "No containers data"}), 400
        for idx, c in enumerate(containers):
            if not c.get('container_type'):
                return jsonify({"success": False, "message": f"Container {idx+1} missing type"}), 400
            items = c.get('items', [])
            if not items or not isinstance(items, list):
                return jsonify({"success": False, "message": f"Container {idx+1} missing items"}), 400
            for item in items:
                if not item.get('model') or item.get('qty') is None:
                    return jsonify({"success": False, "message": f"Container {idx+1} has item missing model or qty"}), 400

        # logistics_contact는 필수
        if not data.get('logistics_contact'):
            return jsonify({"success": False, "message": "Missing required field: logistics_contact"}), 400
        # request_remark는 선택사항

        # 3단계: DB 트랜잭션 시작 및 booking_requests(마스터) 저장
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "message": "DB 연결 실패"}), 500
        try:
            with conn:
                with conn.cursor() as cur:
                    # booking_requests 저장 (3단계)
                    basic = data['basic']
                    logistics_contact_id = data.get('logistics_contact')
                    remark = data.get('request_remark')
                    shipper = basic['shipper']
                    today_str = datetime.now().strftime('%Y%m%d')
                    cur.execute('''
                        SELECT booking_request_number FROM booking_requests
                        WHERE shipper = %s AND booking_request_number LIKE %s
                        ORDER BY booking_request_number DESC LIMIT 1
                    ''', (shipper, f"{shipper}{today_str}%"))
                    last_num = 0
                    row = cur.fetchone()
                    if row and row[0]:
                        last_num = int(row[0][-2:])
                    next_num = last_num + 1
                    booking_request_number = f"{shipper}{today_str}{next_num:02d}"
                    cur.execute('''
                        INSERT INTO booking_requests (
                            booking_request_number, created_by, shipper, shipping_week, to_site, final_destination,
                            consignee, notify, crd, pol, transport_mode, logistics_contact_id, remark, status
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        ) RETURNING id
                    ''', (
                        booking_request_number,
                        session.get('user_id', 1),
                        basic['shipper'],
                        basic['shipping_week'],
                        basic['to_site'],
                        basic['final_destination'],
                        basic['consignee'],
                        basic['notify'],
                        basic['crd'],
                        basic['pol'],
                        basic['transport_mode'],
                        logistics_contact_id,
                        remark,
                        'requested'
                    ))
                    booking_request_id = cur.fetchone()['id']

                    # 4단계: 컨테이너/아이템 정보 저장
                    containers = data['containers']
                    for c in containers:
                        # booking_containers 저장
                        cur.execute('''
                            INSERT INTO booking_containers (booking_request_id, container_type)
                            VALUES (%s, %s) RETURNING id
                        ''', (booking_request_id, c['container_type']))
                        container_id = cur.fetchone()['id']
                        # booking_items 저장
                        for item in c['items']:
                            cur.execute('''
                                INSERT INTO booking_items (container_id, model, qty)
                                VALUES (%s, %s, %s)
                            ''', (container_id, item['model'], item['qty']))
                    # 추가한 내용을 감사/이력(audit_history) 기록 (insert)
                    insert_audit('booking_requests', 'insert', None, None, None,  session.get('username', 'system'), booking_request_id)

            return jsonify({"success": True, "message": "booking 전체 저장 성공", "booking_request_id": booking_request_id})
        finally:
            conn.close()
    except Exception as e:
        print("Booking 저장 에러:", repr(e))
        msg = str(e) if str(e) else "Unknown error"
        return jsonify({"success": False, "message": msg}), 400

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

EMAIL_REGEX = r'^[\w\.-]+@[\w\.-]+\.\w+$'
AVATAR_LIST = [f'avatar{i}.png' for i in range(1, 21)]  # avatar1.png ~ avatar20.png

def convert_date_to_week_format(date_string):
    """날짜를 Week 형식으로 변환 (예: 2025-09-24 -> 2025-09-22(W39))"""
    if not date_string:
        return ""
    
    try:
        # 해당 주의 월요일 찾기
        days_since_monday = date_string.weekday()  # 0=Monday, 6=Sunday
        monday = date_string - timedelta(days=days_since_monday)

        # 주차 계산 (ISO week)
        year = monday.year
        week_number = monday.isocalendar()[1]
        
        # 형식: 2025-09-22(W39)
        formatted_week = f"{monday.strftime('%Y-%m-%d')}(W{week_number:02d})"
        return formatted_week
        
    except ValueError:
        return date_string  # 변환 실패시 원본 반환
    
def insert_audit(table, action, field, old, new, username, record_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO audit_history (table_name, record_id, action, field_name, old_value, new_value, changed_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (
        table, str(record_id), action, field, str(old) if old is not None else None, str(new) if new is not None else None, str(username)
    ))
    conn.commit()
    cursor.close()
    conn.close()

@app.route('/')
def index():
    """메인 페이지 - 대시보드"""
    user_info = None
    is_admin = False
    if 'user_id' in session:
        user_info = {
            'username': session.get('username'),
            'avatar': session.get('avatar'),
            'company': session.get('company'),
            'is_admin': session.get('is_admin')
        }
        is_admin = session.get('is_admin') == 1
    return render_template('index.html', user_info=user_info, is_admin=is_admin)

# 회원 명단 페이지 (관리자만 접근)
@app.route('/users')
def users():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('is_admin') != 1:
        return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, company, job, avatar, approved, is_admin FROM users ORDER BY id')
    user_list = cursor.fetchall()
    # 회사명 리스트 조회 (company 테이블에서 모든 업체명)
    cursor.execute('SELECT name FROM companies WHERE is_terminated = FALSE ORDER BY name')
    company_list = [row['name'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    user_info = {
        'username': session.get('username'),
        'avatar': session.get('avatar'),
        'company': session.get('company'),
        'is_admin': session.get('is_admin')
    }
    return render_template('users.html', user_list=user_list, company_list=company_list, user_info=user_info)

# 로그인 페이지 및 처리
@app.route('/login', methods=['GET', 'POST'])
def login():
    error_message = None
    success = False
    username = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM users WHERE username = %s AND password = %s AND approved = 1
        ''', (username, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['avatar'] = user['avatar']
            session['company'] = user['company']
            session['is_admin'] = user['is_admin']
            success = True
        else:
            error_message = 'Invalid username or password.'
    if success:
        return redirect(url_for('index'))
    return render_template('login.html', error_message=error_message, success=success, username=username)

# 로그아웃 라우트 추가
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# 회원가입 페이지 및 처리
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    error_username = error_email = error_password = error_avatar = error_company = error_job = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        company = request.form.get('company', '').strip()
        job = request.form.get('job', '').strip()
        avatar = request.form.get('avatar', '')

        # Username validation
        if not username:
            error_username = 'Username is required.'
        # Email validation
        if not email or not re.match(EMAIL_REGEX, email):
            error_email = 'Invalid email address format.'
        # Password validation
        if not password or len(password) < 8:
            error_password = 'Password must be at least 8 characters.'
        # Company validation
        if not company:
            error_company = 'Company is required.'
        # Job validation
        if not job:
            error_job = 'Job title is required.'
        # Avatar validation
        if avatar not in AVATAR_LIST:
            error_avatar = 'Please select an avatar.'
        # If no errors, save to DB
        if not (error_username or error_email or error_password or error_company or error_job or error_avatar):
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO users (username, email, password, company, job, avatar, approved, is_admin)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (username, email, password, company, job, avatar, 0, 0))
                conn.commit()
                cursor.close()
                conn.close()
                return render_template('signup.html', success=True, avatar_list=AVATAR_LIST)
            except psycopg2.IntegrityError as e:
                cursor.close()
                conn.close()
                # 에러 메시지에서 어떤 필드가 중복인지 판별
                msg = str(e)
                if 'username' in msg:
                    error_username = 'Username already exists.'
                elif 'email' in msg:
                    error_email = 'Email already exists.'
                else:
                    error_username = 'Username or email already exists.'
            except Exception as e:
                cursor.close()
                conn.close()
                error_username = f'Unexpected error: {str(e)}'
    return render_template('signup.html',
        error_username=error_username,
        error_email=error_email,
        error_password=error_password,
        error_company=error_company,
        error_job=error_job,
        error_avatar=error_avatar,
        avatar_list=AVATAR_LIST
    )

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    """Dashboard 페이지 - 분석 및 통계"""

    # 로그인한 유저 정보는 session에서 바로 가져옴
    user_info = {
        'username': session.get('username'),
        'avatar': session.get('avatar'),
        'company': session.get('company'),
        'is_admin': session.get('is_admin')
    }

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 오늘 날짜의 weekname 및 4주 뒤 weekname 구하기
    today = datetime.today()
    default_weekname = convert_date_to_week_format(today)
    four_weeks_later = today + timedelta(weeks=4)
    default_weekname_to = convert_date_to_week_format(four_weeks_later)
    # 검색 조건 받기 (week_from, week_to 기본값 설정)
    supplier_filter = request.args.get('supplier', '')
    week_from = request.args.get('week_from', default_weekname)
    week_to = request.args.get('week_to', default_weekname_to)

    # 유저의 company type 조회
    user_company = user_info['company']
    cursor.execute('SELECT type FROM companies WHERE name = %s', (user_company,))
    row = cursor.fetchone()
    user_company_type = row['type'] if row else None

    # Supplier 목록 조건 분기
    if user_company_type == 'LG Electronics':
        cursor.execute('''
            SELECT name FROM companies WHERE type = %s AND is_terminated = FALSE
        ''', ('Outsourcing',))
        supplier_list = sorted([row['name'] for row in cursor.fetchall()])
        # 전체 조회용 옵션 추가
        supplier_list = ['All'] + supplier_list
    elif user_company_type == 'Outsourcing':
        supplier_list = [user_company]
    else:
        supplier_list = []
        
    if request.args:  # Search 버튼을 눌렀을 때만 DB 조회
        # Shipment Plans 쿼리 조건 구성
        sp_conditions = ["is_deleted = FALSE"]
        sp_params = []
        if supplier_filter:
            sp_conditions.append("from_site = %s")
            sp_params.append(supplier_filter)
        if week_from:
            sp_conditions.append("shipping_week >= %s")
            sp_params.append(week_from)
        if week_to:
            sp_conditions.append("shipping_week <= %s")
            sp_params.append(week_to)
        sp_where_clause = " AND ".join(sp_conditions)
        # Shipment Plans 데이터 조회
        cursor.execute(f'''
            SELECT from_site, to_site, model_name, shipping_week, shipping_quantity 
            FROM shipping_plans 
            WHERE {sp_where_clause}
        ''', sp_params)
        shipment_plans = cursor.fetchall()

        # Purchase Orders 쿼리 조건 구성
        po_conditions = ["status = 'Active'"]
        po_params = []
        if supplier_filter:
            po_conditions.append("from_site = %s")
            po_params.append(supplier_filter)
        if week_from:
            po_conditions.append("rsd >= %s")
            po_params.append(week_from[:10])  # yyyy-mm-dd 부분만 추출
        if week_to:
            po_conditions.append("rsd <= %s")
            po_params.append(week_to[:10])   # yyyy-mm-dd 부분만 추출
        # Purchase Orders 데이터 조회
        cursor.execute(f'''
            SELECT po_number, from_site, to_site, model, po_qty, rsd, status 
            FROM purchase_orders 
            WHERE {" AND ".join(po_conditions)}
        ''', po_params)
        purchase_orders = cursor.fetchall()
        cursor.close()
        conn.close()
        # 피벗 테이블 생성
        result = create_pivot_table(shipment_plans, purchase_orders)
        return render_template('dashboard.html', 
            pivot_data=result['pivot_data'],
            weeks=result['weeks'],
            week_totals=result['week_totals'],
            grand_totals=result['grand_totals'],
            overall_total=result['overall_total'],
            suppliers=supplier_list,
            search_executed=True,
            user_info=user_info,
            default_weekname=default_weekname,
            default_weekname_to=default_weekname_to,
            week_from=week_from,
            week_to=week_to)
    else:
        cursor.close()
        conn.close()
        # 검색 조건이 없으면 필터 폼만 표시 (빈 데이터로 초기화)
    return render_template('dashboard.html',
        pivot_data={},  
        weeks=[],  
        week_totals={},
        grand_totals={},
        overall_total={},
        suppliers=supplier_list,
        search_executed=False,
        user_info=user_info,
        default_weekname=default_weekname,
        default_weekname_to=default_weekname_to,
        week_from=week_from,
        week_to=week_to)

def create_pivot_table(shipment_plans, purchase_orders):
    """피벗 테이블 데이터 생성"""
    
    # 데이터 구조: {to_site: {week: {'po': qty, 'sp': qty, 'details': {'sp': [records], 'po': [records]}}}}
    pivot = defaultdict(lambda: defaultdict(lambda: {'po': 0, 'sp': 0, 'details': {'sp': [], 'po': []}}))
    
    # 모든 Week 수집용
    all_weeks = set()
    
    # Shipment Plans 데이터 처리
    for plan in shipment_plans:
        to_site = plan['to_site']
        week = plan['shipping_week']
        quantity = plan['shipping_quantity']
        
        pivot[to_site][week]['sp'] += quantity
        pivot[to_site][week]['details']['sp'].append({
            'from_site': plan['from_site'],
            'model_name': plan['model_name'],
            'quantity': quantity,
            'week': week
        })
        all_weeks.add(week)
    
    # Purchase Orders 데이터 처리 (rsd를 Week 형식으로 변환)
    for po in purchase_orders:
        to_site = po['to_site']  # 정규화 제거
        rsd = po['rsd']
        if rsd:
            rsd_str = rsd.strftime('%Y-%m-%d')
        else:
            rsd_str = ''
        quantity = po['po_qty']
        
        # RSD를 Week 형식으로 변환
        week = convert_date_to_week_format(rsd)
        
        if week:  # 변환이 성공한 경우만
            pivot[to_site][week]['po'] += quantity
            pivot[to_site][week]['details']['po'].append({
                'po_number': po['po_number'],
                'from_site': po['from_site'],
                'model': po['model'],
                'quantity': quantity,
                'rsd': rsd_str,
                'status': po['status']
            })
            all_weeks.add(week)
    
    # Week 정렬 (시간순)
    sorted_weeks = sorted(list(all_weeks), key=lambda x: x if x else '')
    
    # To Site 정렬 (알파벳순)
    sorted_sites = sorted(pivot.keys())
    
    # Total 계산
    week_totals = {}
    for site in sorted_sites:
        site_sp_total = 0
        site_po_total = 0
        for week in sorted_weeks:
            if week in pivot[site]:
                site_sp_total += pivot[site][week]['sp']
                site_po_total += pivot[site][week]['po']
        week_totals[site] = {
            'sp': site_sp_total,
            'po': site_po_total
        }
    
    # Weekly Total 계산 (Grand Totals)
    grand_totals = {}
    for week in sorted_weeks:
        week_sp_total = 0
        week_po_total = 0
        for site in sorted_sites:
            if week in pivot[site]:
                week_sp_total += pivot[site][week]['sp']
                week_po_total += pivot[site][week]['po']
        grand_totals[week] = {
            'sp': week_sp_total,
            'po': week_po_total
        }
    
    # Overall Total 계산
    overall_sp_total = sum(week_totals[site]['sp'] for site in sorted_sites)
    overall_po_total = sum(week_totals[site]['po'] for site in sorted_sites)
    
    return {
        'pivot_data': dict(pivot),
        'weeks': sorted_weeks,
        'sites': sorted_sites,
        'week_totals': week_totals,
        'grand_totals': grand_totals,
        'overall_total': {
            'sp': overall_sp_total,
            'po': overall_po_total
        }
    }

@app.route('/add_shipment', methods=['POST'])
def add_shipment():
    """새로운 선적계획 추가 (Shipment 페이지용)"""
    from_site = request.form['from_site'].strip()
    to_site = request.form['to_site'].strip()
    model_name = request.form['model_name'].strip()
    shipping_week_date = request.form['shipping_week_date']
    shipping_quantity = int(request.form['shipping_quantity'])
    remark = request.form.get('remark', '').strip()
    
    # 날짜를 Week 형식으로 변환
    shipping_week = convert_date_to_week_format(datetime.strptime(shipping_week_date, '%Y-%m-%d'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO shipping_plans (from_site, to_site, model_name, shipping_week, shipping_quantity, remark)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (from_site, to_site, model_name, shipping_week, shipping_quantity, remark))
    plan_id = cursor.fetchone()['id']
    # 감사(audit) 히스토리 기록 (INSERT)
    changed_by = session.get('username', 'unknown')
    cursor.execute('''
        INSERT INTO audit_history (table_name, record_id, action, field_name, old_value, new_value, changed_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (
        'shipping_plans', str(plan_id), 'INSERT', None, None, None, changed_by
    ))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('shipment'))

@app.route('/update/<int:id>', methods=['POST'])
def update_plan(id):
    """선적계획 수정"""
    from_site = request.form['from_site']
    to_site = request.form['to_site']
    model_name = request.form['model_name']
    # 날짜를 Week 형식으로 변환 (프론트엔드에서 항상 shipping_week_date를 전달)
    shipping_week = convert_date_to_week_format(datetime.strptime(request.form['shipping_week_date'], '%Y-%m-%d'))
    shipping_quantity = int(request.form['shipping_quantity'])
    remark = request.form.get('remark', '').strip()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # 기존 데이터 조회
    cursor.execute('SELECT * FROM shipping_plans WHERE id = %s', (id,))
    old_data = cursor.fetchone()
    # 데이터 업데이트
    cursor.execute('''
        UPDATE shipping_plans 
        SET from_site = %s, to_site = %s, model_name = %s, shipping_week = %s, shipping_quantity = %s, remark = %s, updated_at = NOW()
        WHERE id = %s
    ''', (from_site, to_site, model_name, shipping_week, shipping_quantity, remark, id))
    conn.commit()
    cursor.close()
    conn.close()

    # 변경된 필드 audit_history 기록
    username = session.get('username', 'unknown')
    if old_data['from_site'] != from_site:
        insert_audit('shipping_plans', 'update', 'from_site', old_data['from_site'], from_site, username, id)
    if old_data['to_site'] != to_site:
        insert_audit('shipping_plans', 'update', 'to_site', old_data['to_site'], to_site, username, id)
    if old_data['model_name'] != model_name:
        insert_audit('shipping_plans', 'update', 'model_name', old_data['model_name'], model_name, username, id)
    if old_data['shipping_week'] != shipping_week:
        insert_audit('shipping_plans', 'update', 'shipping_week', old_data['shipping_week'], shipping_week, username, id)
    if old_data['shipping_quantity'] != shipping_quantity:
        insert_audit('shipping_plans', 'update', 'shipping_quantity', old_data['shipping_quantity'], shipping_quantity, username, id)
    if (old_data['remark'] or '') != remark:
        insert_audit('shipping_plans', 'update', 'remark', old_data['remark'] if old_data['remark'] is not None else '', remark, username, id)

    return redirect(url_for('shipment'))

@app.route('/delete/<int:id>', methods=['POST'])
def delete_plan(id):
    """선적계획 삭제 (소프트 삭제)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # 소프트 삭제 (삭제 시점도 updated_at에 기록)
    cursor.execute('UPDATE shipping_plans SET is_deleted = TRUE, updated_at = NOW() WHERE id = %s', (id,))

    # 삭제 이력 audit_history 기록
    username = session.get('username', 'unknown')
    cursor.execute('''
        INSERT INTO audit_history (table_name, record_id, action, field_name, old_value, new_value, changed_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (
        'shipping_plans', str(id), 'delete', None, None, None, username
    ))

    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('shipment'))

@app.route('/history/<int:id>')
def view_history(id):
    """특정 선적계획의 히스토리 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # 선적계획 기본 정보 + 한국시간 변환 컬럼 함께 조회
    cursor.execute('''
        SELECT *, 
            created_at AT TIME ZONE 'Asia/Seoul' AS created_at_kst,
            updated_at AT TIME ZONE 'Asia/Seoul' AS updated_at_kst
        FROM shipping_plans WHERE id = %s
    ''', (id,))
    plan = cursor.fetchone()
    cursor.execute('''
        SELECT *, changed_at AT TIME ZONE 'Asia/Seoul' AS changed_at_kst
        FROM audit_history
        WHERE table_name = %s AND record_id = %s
        ORDER BY changed_at DESC
    ''', ('shipping_plans', str(id)))
    history = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('history.html', plan=plan, history=history)

# Shipment page route
@app.route('/shipment')
def shipment():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    """Shipment page - Show shipping plans with search filter"""
    # 로그인한 유저 정보
    user_info = {
        'username': session.get('username'),
        'avatar': session.get('avatar'),
        'company': session.get('company'),
        'is_admin': session.get('is_admin')
    }
    conn = get_db_connection()
    cursor = conn.cursor()

    # 기본 week 값 계산
    today = datetime.today()
    default_weekname = convert_date_to_week_format(today)
    four_weeks_later = today + timedelta(weeks=4)
    default_weekname_to = convert_date_to_week_format(four_weeks_later)

    # 검색 조건 받기
    supplier_filter = request.args.get('supplier', '')
    week_from = request.args.get('week_from', default_weekname)
    week_to = request.args.get('week_to', default_weekname_to)

    # 유저의 company type 조회
    user_company = user_info['company']
    cursor.execute('SELECT type FROM companies WHERE name = %s', (user_company,))
    row = cursor.fetchone()
    user_company_type = row['type'] if row else None

    # Supplier 목록 조건 분기
    if user_company_type == 'LG Electronics':
        cursor.execute('''
            SELECT name FROM companies WHERE type = %s AND is_terminated = FALSE
        ''', ('Outsourcing',))
        supplier_list = sorted([row['name'] for row in cursor.fetchall()])
        supplier_list = ['All'] + supplier_list
    elif user_company_type == 'Outsourcing':
        supplier_list = [user_company]
    else:
        supplier_list = []

    plans = []
    search_executed = False
    if request.args:  # Search 버튼을 눌렀을 때만 DB 조회
        search_executed = True
        sp_conditions = ["is_deleted = FALSE"]
        sp_params = []
        if supplier_filter:
            sp_conditions.append("from_site = %s")
            sp_params.append(supplier_filter)
        if week_from:
            sp_conditions.append("shipping_week >= %s")
            sp_params.append(week_from)
        if week_to:
            sp_conditions.append("shipping_week <= %s")
            sp_params.append(week_to)
        sp_where_clause = " AND ".join(sp_conditions)
        cursor.execute(f'''
            SELECT * FROM shipping_plans
            WHERE {sp_where_clause}
            ORDER BY id DESC
        ''', sp_params)
        plans = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('shipment.html',
        plans=plans,
        user_info=user_info,
        suppliers=supplier_list,
        week_from=week_from,
        week_to=week_to,
        default_weekname=default_weekname,
        default_weekname_to=default_weekname_to,
        search_executed=search_executed
    )

# PO page route
@app.route('/po')
def po():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    """PO page - Show purchase orders with search filter"""
    user_info = {
        'username': session.get('username'),
        'avatar': session.get('avatar'),
        'company': session.get('company'),
        'is_admin': session.get('is_admin')
    }
    conn = get_db_connection()
    cursor = conn.cursor()

    # 기본 week 값 계산
    today = datetime.today()
    default_weekname = convert_date_to_week_format(today)
    four_weeks_later = today + timedelta(weeks=4)
    default_weekname_to = convert_date_to_week_format(four_weeks_later)

    # 검색 조건 받기
    supplier_filter = request.args.get('supplier', '')
    week_from = request.args.get('week_from', default_weekname)
    week_to = request.args.get('week_to', default_weekname_to)

    # 유저의 company type 조회
    user_company = user_info['company']
    cursor.execute('SELECT type FROM companies WHERE name = %s', (user_company,))
    row = cursor.fetchone()
    user_company_type = row['type'] if row else None

    # Supplier 목록 조건 분기
    if user_company_type == 'LG Electronics':
        cursor.execute('''
            SELECT name FROM companies WHERE type = %s AND is_terminated = FALSE
        ''', ('Outsourcing',))
        supplier_list = sorted([row['name'] for row in cursor.fetchall()])
        supplier_list = ['All'] + supplier_list
    elif user_company_type == 'Outsourcing':
        supplier_list = [user_company]
    else:
        supplier_list = []

    pos = []
    search_executed = False
    if request.args:  # Search 버튼을 눌렀을 때만 DB 조회
        search_executed = True
        po_conditions = ["status = 'Active'"]
        po_params = []
        if supplier_filter:
            po_conditions.append("from_site = %s")
            po_params.append(supplier_filter)
        if week_from:
            po_conditions.append("rsd >= %s")
            po_params.append(week_from[:10])  # yyyy-mm-dd 부분만 추출
        if week_to:
            po_conditions.append("rsd <= %s")
            po_params.append(week_to[:10])   # yyyy-mm-dd 부분만 추출
        po_where_clause = " AND ".join(po_conditions)
        cursor.execute(f'''
            SELECT * FROM purchase_orders
            WHERE {po_where_clause}
            ORDER BY id DESC
        ''', po_params)
        pos = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('po.html',
        pos=pos,
        user_info=user_info,
        suppliers=supplier_list,
        week_from=week_from,
        week_to=week_to,
        default_weekname=default_weekname,
        default_weekname_to=default_weekname_to,
        search_executed=search_executed
    )

@app.route('/add_po', methods=['POST'])
def add_po():
    """Add new purchase order"""
    po_number = request.form['po_number'].strip()
    from_site = request.form['from_site'].strip()
    to_site = request.form['to_site'].strip()
    model = request.form['model'].strip()
    po_qty = int(request.form['po_qty'])
    rsd = request.form['rsd']
    remark = request.form.get('remark', '').strip()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO purchase_orders (po_number, from_site, to_site, model, po_qty, rsd, remark)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (po_number, from_site, to_site, model, po_qty, rsd, remark))
        po_id = cursor.fetchone()['id']
        changed_by = session.get('username', 'unknown')
        cursor.execute('''
            INSERT INTO audit_history (table_name, record_id, action, field_name, old_value, new_value, changed_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (
            'purchase_orders', str(po_id), 'INSERT', None, None, None, changed_by
        ))
        conn.commit()
    except psycopg2.IntegrityError as e:
        # 에러 발생 시에도 기존 PO 목록을 함께 전달
        cursor.execute('''
            SELECT * FROM purchase_orders 
            WHERE status = 'Active' 
            ORDER BY id DESC
        ''')
        pos = cursor.fetchall()
        cursor.close()
        conn.close()
        if 'duplicate key value violates unique constraint' in str(e):
            return render_template('po.html', pos=pos, error='PO Number already exists! Please use a different PO number.')
        else:
            return render_template('po.html', pos=pos, error='Database error occurred.')
    cursor.close()
    conn.close()
    return redirect(url_for('po'))

@app.route('/update_po/<int:id>', methods=['POST'])
def update_po(id):
    """Update purchase order"""
    po_number = request.form['po_number']
    from_site = request.form['from_site']
    to_site = request.form['to_site']
    model = request.form['model']
    po_qty = int(request.form['po_qty'])
    rsd = request.form['rsd']
    remark = request.form.get('remark', '').strip()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # 기존 데이터 조회
    cursor.execute('SELECT * FROM purchase_orders WHERE id = %s', (id,))
    old_data = cursor.fetchone()

    # 데이터 업데이트
    cursor.execute('''
        UPDATE purchase_orders 
        SET po_number = %s, from_site = %s, to_site = %s, model = %s, po_qty = %s, rsd = %s, remark = %s, 
            last_update = NOW()
        WHERE id = %s
    ''', (po_number, from_site, to_site, model, po_qty, rsd, remark, id))
    conn.commit()
    cursor.close()
    conn.close()
    
    # 변경된 필드 히스토리 기록
    username = session.get('username', 'unknown')
    if old_data['po_number'] != po_number:
        insert_audit('purchase_orders', 'update', 'po_number', old_data['po_number'], po_number, username, id)
    if old_data['from_site'] != from_site:
        insert_audit('purchase_orders', 'update', 'from_site', old_data['from_site'], from_site, username, id)
    if old_data['to_site'] != to_site:
        insert_audit('purchase_orders', 'update', 'to_site', old_data['to_site'], to_site, username, id)
    if old_data['model'] != model:
        insert_audit('purchase_orders', 'update', 'model', old_data['model'], model, username, id)
    if old_data['po_qty'] != po_qty:
        insert_audit('purchase_orders', 'update', 'po_qty', str(old_data['po_qty']), str(po_qty), username, id)
    if str(old_data['rsd']) != rsd:
        insert_audit('purchase_orders', 'update', 'rsd', old_data['rsd'], rsd, username, id)
    if (old_data['remark'] or '') != remark:
        insert_audit('purchase_orders', 'update', 'remark', old_data['remark'] or '', remark, username, id)
    
    return jsonify({'success': True})

@app.route('/delete_po/<int:id>', methods=['POST'])
def delete_po(id):
    """Delete purchase order (soft delete)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE purchase_orders 
        SET status = 'Inactive', last_update = NOW() 
        WHERE id = %s
    ''', (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('po'))

@app.route('/po_history/<int:id>')
def po_history(id):
    """View purchase order history"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # PO information (with KST time fields)
    cursor.execute('''
        SELECT *,
            created_at AT TIME ZONE 'Asia/Seoul' AS created_at_kst,
            last_update AT TIME ZONE 'Asia/Seoul' AS last_update_kst
        FROM purchase_orders WHERE id = %s
    ''', (id,))
    po = cursor.fetchone()
    # PO history information (from audit_history, with KST time)
    cursor.execute('''
        SELECT *, changed_at AT TIME ZONE 'Asia/Seoul' AS changed_at_kst
        FROM audit_history
        WHERE table_name = %s AND record_id = %s
        ORDER BY changed_at DESC
    ''', ('purchase_orders', str(id)))
    history = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('po_history.html', po=po, history=history)

@app.route('/update_user/<int:user_id>', methods=['POST'])
def update_user(user_id):
    if 'user_id' not in session or session.get('is_admin') != 1:
        return jsonify({'success': False, 'error': 'Permission denied.'}), 403
    data = request.get_json()
    company = data.get('company', '').strip()
    approved = int(data.get('approved', 0))
    is_admin = int(data.get('is_admin', 0))
    conn = get_db_connection()
    cursor = conn.cursor()
    # 회사명 유효성 체크 삭제
    # DB 업데이트
    cursor.execute('UPDATE users SET company = %s, approved = %s, is_admin = %s WHERE id = %s', (company, approved, is_admin, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/booking')
def booking():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_info = {
        'username': session.get('username'),
        'avatar': session.get('avatar'),
        'company': session.get('company'),
        'is_admin': session.get('is_admin')
    }

    conn = get_db_connection()
    cursor = conn.cursor()
    today = datetime.today()
    default_weekname = convert_date_to_week_format(today)
    four_weeks_later = today + timedelta(weeks=4)
    default_weekname_to = convert_date_to_week_format(four_weeks_later)

    supplier_filter = request.args.get('supplier', '')
    to_site_filter = request.args.get('to_site', '')
    week_from = request.args.get('week_from', default_weekname)
    week_to = request.args.get('week_to', default_weekname_to)

    user_company = user_info['company']
    cursor.execute('SELECT type FROM companies WHERE name = %s', (user_company,))
    row = cursor.fetchone()
    user_company_type = row['type'] if row else None

    if user_company_type == 'LG Electronics':
        cursor.execute('''
            SELECT name FROM companies WHERE type = %s AND is_terminated = FALSE
        ''', ('Outsourcing',))
        supplier_list = sorted([row['name'] for row in cursor.fetchall()])
        supplier_list = ['All'] + supplier_list
    elif user_company_type == 'Outsourcing':
        supplier_list = [user_company]
    else:
        supplier_list = []

    plans = []
    search_executed = False
    if request.args:
        search_executed = True
        # shipping_plans 조회
        sp_conditions = ["is_deleted = FALSE"]
        sp_params = []
        if supplier_filter:
            sp_conditions.append("from_site = %s")
            sp_params.append(supplier_filter)
        if to_site_filter:
            sp_conditions.append("to_site ILIKE %s")
            sp_params.append(f"%{to_site_filter}%")
        if week_from:
            sp_conditions.append("shipping_week >= %s")
            sp_params.append(week_from)
        if week_to:
            sp_conditions.append("shipping_week <= %s")
            sp_params.append(week_to)
        sp_where_clause = " AND ".join(sp_conditions)
        cursor.execute(f'''
            SELECT * FROM shipping_plans
            WHERE {sp_where_clause}
            ORDER BY id DESC
        ''', sp_params)
        plans = cursor.fetchall()

        # purchase_orders 조회
        po_conditions = ["status = 'Active'"]
        po_params = []
        if supplier_filter:
            po_conditions.append("from_site = %s")
            po_params.append(supplier_filter)
        if to_site_filter:
            po_conditions.append("to_site ILIKE %s")
            po_params.append(f"%{to_site_filter}%")
        if week_from:
            po_conditions.append("rsd >= %s")
            po_params.append(week_from[:10])
        if week_to:
            po_conditions.append("rsd <= %s")
            po_params.append(week_to[:10])
        po_where_clause = " AND ".join(po_conditions)
        cursor.execute(f'''
            SELECT po_number, from_site, to_site, model, po_qty, rsd FROM purchase_orders
            WHERE {po_where_clause}
            ORDER BY id DESC
        ''', po_params)
        po_rows = cursor.fetchall()

        # PO의 RSD를 weekname으로 변환하여 매칭용 dict 생성
        po_map = {}
        for po in po_rows:
            weekname = convert_date_to_week_format(po['rsd']) if po['rsd'] else ''
            key = (po['from_site'], po['to_site'], po['model'], weekname)
            po_map[key] = po

        # plans에 PO 정보 매칭
        for plan in plans:
            key = (plan['from_site'], plan['to_site'], plan['model_name'], plan['shipping_week'])
            po = po_map.get(key)
            if po:
                plan['po_number'] = po['po_number']
                plan['po_qty'] = po['po_qty']
            else:
                plan['po_number'] = '-'
                plan['po_qty'] = '-'
    # Fetch logistics company users for Contact Person selection
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.id, u.username, u.email, u.avatar, c.name AS company_name
        FROM users u
        JOIN companies c ON u.company = c.name
        WHERE c.type = %s AND c.is_terminated = FALSE
        ORDER BY c.name, u.username
    ''', ('Logistics',))
    logistics_users = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('booking.html',
        user_info=user_info,
        suppliers=supplier_list,
        default_weekname=default_weekname,
        default_weekname_to=default_weekname_to,
        week_from=week_from,
        week_to=week_to,
        to_site=to_site_filter,
        search_executed=search_executed,
        plans=plans,
        logistics_users=logistics_users
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))