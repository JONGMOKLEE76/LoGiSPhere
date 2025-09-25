import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import re
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import sqlite3
from datetime import datetime, timedelta
import os

# Load environment variables
load_dotenv()   

app = Flask(__name__)
app.secret_key = 'b7f2e8c1-4a2d-4e9a-9c3e-8f1d2a7b6c5e'  # 안전한 랜덤 문자열

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
        # 입력 날짜 파싱
        selected_date = datetime.strptime(date_string, '%Y-%m-%d')
        
        # 해당 주의 월요일 찾기
        days_since_monday = selected_date.weekday()  # 0=Monday, 6=Sunday
        monday = selected_date - timedelta(days=days_since_monday)
        
        # 주차 계산 (ISO week)
        year = monday.year
        week_number = monday.isocalendar()[1]
        
        # 형식: 2025-09-22(W39)
        formatted_week = f"{monday.strftime('%Y-%m-%d')}(W{week_number:02d})"
        return formatted_week
        
    except ValueError:
        return date_string  # 변환 실패시 원본 반환

def log_history(plan_id, field_name=None, old_value=None, new_value=None):
    """히스토리 로그 기록"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO shipping_plans_history (plan_id, field_name, old_value, new_value)
        VALUES (%s, %s, %s, %s)
    ''', (plan_id, field_name, old_value, new_value))
    conn.commit()
    cursor.close()
    conn.close()

def log_po_history(po_id, field_name=None, old_value=None, new_value=None):
    """PO 히스토리 로그 기록"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO purchase_orders_history (po_id, field_name, old_value, new_value)
        VALUES (%s, %s, %s, %s)
    ''', (po_id, field_name, old_value, new_value))
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
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 검색 조건 받기
    supplier_filter = request.args.get('supplier', '')
    week_from = request.args.get('week_from', '')
    week_to = request.args.get('week_to', '')

    # 로그인한 유저 정보는 session에서 바로 가져옴
    user_info = {
        'username': session.get('username'),
        'avatar': session.get('avatar'),
        'company': session.get('company'),
        'is_admin': session.get('is_admin')
    }

    # 검색이 실행되었는지 확인 (GET 파라미터가 하나라도 있으면 검색 실행된 것으로 간주)
    search_executed = bool(request.args)

    # 검색 조건이 있는지 확인 (실제 필터 값이 있는지)
    has_search_conditions = bool(supplier_filter or week_from or week_to)
    
    # Supplier 목록 조회 (companies 테이블에서 Outsourcing 업체만)
    cursor.execute('''
        SELECT name FROM companies WHERE type = %s AND is_terminated = FALSE
    ''', ('Outsourcing',))
    supplier_list = sorted([row['name'] for row in cursor.fetchall()])
    
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
    
    # Supplier 필터를 from_site로 적용
    if supplier_filter:
        po_conditions.append("from_site = %s")
        po_params.append(supplier_filter)

    # Week 범위를 날짜로 변환하여 SQL에서 직접 처리
    if week_from:
        po_conditions.append("rsd >= %s")
        po_params.append(week_from[:10])  # yyyy-mm-dd 부분만 추출

    if week_to:
        po_conditions.append("rsd <= %s")
        po_params.append(week_to[:10])   # yyyy-mm-dd 부분만 추출
    
    # Purchase Orders 데이터 조회 - try-except 제거
    cursor.execute(f'''
        SELECT po_number, from_site, to_site, model, po_qty, rsd, status 
        FROM purchase_orders 
        WHERE {" AND ".join(po_conditions)}
    ''', po_params)
    purchase_orders = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    # 검색이 실행되었을 때 피벗 테이블 생성 (조건 유무와 관계없이)
    if search_executed:
        # 피벗 테이블 생성
        result = create_pivot_table(shipment_plans, purchase_orders)
        
        return render_template('dashboard.html', 
                             pivot_data=result['pivot_data'],
                             weeks=result['weeks'],
                             week_totals=result['week_totals'],
                             grand_totals=result['grand_totals'],
                             overall_total=result['overall_total'],
                             suppliers=supplier_list,
                             search_executed=search_executed,
                             has_search_conditions=has_search_conditions,
                             user_info=user_info)
    else:
        # 검색이 실행되지 않았으면 필터 폼만 표시 (빈 데이터로 초기화)
        return render_template('dashboard.html',
                             pivot_data={},
                             weeks=[],  
                             week_totals={},
                             grand_totals={},
                             overall_total={},
                             suppliers=supplier_list,
                             search_executed=search_executed,
                             has_search_conditions=has_search_conditions,
                             user_info=user_info)

def create_pivot_table(shipment_plans, purchase_orders):
    """피벗 테이블 데이터 생성"""
    from collections import defaultdict
    
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
                'rsd': rsd,
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
    shipping_week = convert_date_to_week_format(shipping_week_date)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO shipping_plans (from_site, to_site, model_name, shipping_week, shipping_quantity, remark)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (from_site, to_site, model_name, shipping_week, shipping_quantity, remark))
    conn.commit()
    cursor.close()
    conn.close()
    # 생성은 created_at으로 추적 가능하므로 히스토리에 기록하지 않음
    return redirect(url_for('shipment'))

@app.route('/update/<int:id>', methods=['POST'])
def update_plan(id):
    """선적계획 수정"""
    from_site = request.form['from_site']
    to_site = request.form['to_site']
    model_name = request.form['model_name']
    
    # 날짜를 Week 형식으로 변환 (인라인 편집에서)
    if 'shipping_week_date' in request.form:
        shipping_week = convert_date_to_week_format(request.form['shipping_week_date'])
    else:
        shipping_week = request.form['shipping_week']  # 기존 방식 호환
    
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
    
    # 변경된 필드 히스토리 기록
    if old_data['from_site'] != from_site:
        log_history(id, 'from_site', old_data['from_site'], from_site)
    if old_data['to_site'] != to_site:
        log_history(id, 'to_site', old_data['to_site'], to_site)
    if old_data['model_name'] != model_name:
        log_history(id, 'model_name', old_data['model_name'], model_name)
    if old_data['shipping_week'] != shipping_week:
        log_history(id, 'shipping_week', old_data['shipping_week'], shipping_week)
    if old_data['shipping_quantity'] != shipping_quantity:
        log_history(id, 'shipping_quantity', str(old_data['shipping_quantity']), str(shipping_quantity))
    if (old_data['remark'] or '') != remark:
        log_history(id, 'remark', old_data['remark'] or '', remark)
    
    return redirect(url_for('shipment'))

@app.route('/delete/<int:id>', methods=['POST'])
def delete_plan(id):
    """선적계획 삭제 (소프트 삭제)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # 소프트 삭제 (삭제 시점도 updated_at에 기록)
    cursor.execute('UPDATE shipping_plans SET is_deleted = TRUE, updated_at = NOW() WHERE id = %s', (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('shipment'))

@app.route('/history/<int:id>')
def view_history(id):
    """특정 선적계획의 히스토리 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    # 계획 정보
    cursor.execute('SELECT * FROM shipping_plans WHERE id = %s', (id,))
    plan = cursor.fetchone()
    # 히스토리 정보
    cursor.execute('''
        SELECT * FROM shipping_plans_history 
        WHERE plan_id = %s 
        ORDER BY changed_at DESC
    ''', (id,))
    history = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('history.html', plan=plan, history=history)

# Shipment page route
@app.route('/shipment')
def shipment():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    """Shipment page - Show shipping plans"""
    # 로그인한 유저 정보는 session에서 바로 가져옴
    user_info = None
    if 'user_id' in session:
        user_info = {
            'username': session.get('username'),
            'avatar': session.get('avatar'),
            'company': session.get('company'),
            'is_admin': session.get('is_admin')
        }
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM shipping_plans 
        WHERE is_deleted = FALSE 
        ORDER BY id DESC
    ''')
    plans = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('shipment.html', plans=plans, user_info=user_info)

# PO page route
@app.route('/po')
def po():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    """PO page - Show purchase orders"""
    # 로그인한 유저 정보는 session에서 바로 가져옴
    user_info = None
    if 'user_id' in session:
        user_info = {
            'username': session.get('username'),
            'avatar': session.get('avatar'),
            'company': session.get('company'),
            'is_admin': session.get('is_admin')
        }
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM purchase_orders 
        WHERE status = 'Active' 
        ORDER BY id DESC
    ''')
    pos = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('po.html', pos=pos, user_info=user_info)

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
        ''', (po_number, from_site, to_site, model, po_qty, rsd, remark))
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
    if old_data['po_number'] != po_number:
        log_po_history(id, 'po_number', old_data['po_number'], po_number)
    if old_data['from_site'] != from_site:
        log_po_history(id, 'from_site', old_data['from_site'], from_site)
    if old_data['to_site'] != to_site:
        log_po_history(id, 'to_site', old_data['to_site'], to_site)
    if old_data['model'] != model:
        log_po_history(id, 'model', old_data['model'], model)
    if old_data['po_qty'] != po_qty:
        log_po_history(id, 'po_qty', str(old_data['po_qty']), str(po_qty))
    if old_data['rsd'] != rsd:
        log_po_history(id, 'rsd', old_data['rsd'], rsd)
    if (old_data['remark'] or '') != remark:
        log_po_history(id, 'remark', old_data['remark'] or '', remark)
    
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
    # PO information
    cursor.execute('SELECT * FROM purchase_orders WHERE id = %s', (id,))
    po = cursor.fetchone()
    # PO history information
    cursor.execute('''
        SELECT * FROM purchase_orders_history 
        WHERE po_id = %s 
        ORDER BY changed_at DESC
    ''', (id,))
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
    # 회사명 유효성 체크
    cursor.execute('SELECT name FROM companies WHERE is_terminated = FALSE')
    valid_companies = set(row['name'] for row in cursor.fetchall())
    if company not in valid_companies:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': 'Selected company is not valid.'}), 400
    # DB 업데이트
    cursor.execute('UPDATE users SET company = %s, approved = %s, is_admin = %s WHERE id = %s', (company, approved, is_admin, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)