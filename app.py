from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)

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

def get_db_connection():
    """데이터베이스 연결"""
    conn = sqlite3.connect('shipping_plan.db')
    conn.row_factory = sqlite3.Row
    return conn

def log_history(plan_id, field_name=None, old_value=None, new_value=None):
    """히스토리 로그 기록"""
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO shipping_plans_history (plan_id, field_name, old_value, new_value)
        VALUES (?, ?, ?, ?)
    ''', (plan_id, field_name, old_value, new_value))
    conn.commit()
    conn.close()

def log_po_history(po_id, field_name=None, old_value=None, new_value=None):
    """PO 히스토리 로그 기록"""
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO purchase_orders_history (po_id, field_name, old_value, new_value)
            VALUES (?, ?, ?, ?)
        ''', (po_id, field_name, old_value, new_value))
    except sqlite3.OperationalError:
        # PO history table doesn't exist, create it first
        conn.execute('''
            CREATE TABLE IF NOT EXISTS purchase_orders_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                po_id INTEGER NOT NULL,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                changed_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (po_id) REFERENCES purchase_orders (id)
            )
        ''')
        conn.execute('''
            INSERT INTO purchase_orders_history (po_id, field_name, old_value, new_value)
            VALUES (?, ?, ?, ?)
        ''', (po_id, field_name, old_value, new_value))
    conn.commit()
    conn.close()

@app.route('/')
def index():
    """메인 페이지 - 대시보드"""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """Dashboard 페이지 - 분석 및 통계"""
    conn = get_db_connection()
    
    # 검색 조건 받기
    supplier_filter = request.args.get('supplier', '')
    week_from = request.args.get('week_from', '')
    week_to = request.args.get('week_to', '')
    
    # 검색이 실행되었는지 확인 (GET 파라미터가 하나라도 있으면 검색 실행된 것으로 간주)
    search_executed = bool(request.args)
    
    # 검색 조건이 있는지 확인 (실제 필터 값이 있는지)
    has_search_conditions = bool(supplier_filter or week_from or week_to)
    
    # Supplier 목록 조회 (드롭다운용) - SP의 from_site와 PO의 from_site를 합침
    sp_suppliers = conn.execute('''
        SELECT DISTINCT from_site as supplier_name
        FROM shipping_plans 
        WHERE is_deleted = FALSE
    ''').fetchall()
    
    try:
        po_suppliers = conn.execute('''
            SELECT DISTINCT from_site as supplier_name
            FROM purchase_orders 
            WHERE status = 'Active'
        ''').fetchall()
    except sqlite3.OperationalError:
        po_suppliers = []
    
    # 두 목록을 합치고 중복 제거
    all_suppliers = set()
    for row in sp_suppliers:
        all_suppliers.add(row['supplier_name'])
    for row in po_suppliers:
        all_suppliers.add(row['supplier_name'])
    
    supplier_list = sorted(list(all_suppliers))
    
    # Shipment Plans 쿼리 조건 구성
    sp_conditions = ["is_deleted = FALSE"]
    sp_params = []
    
    if supplier_filter:
        sp_conditions.append("from_site = ?")
        sp_params.append(supplier_filter)
    
    if week_from:
        sp_conditions.append("shipping_week >= ?")
        sp_params.append(week_from)
    
    if week_to:
        sp_conditions.append("shipping_week <= ?")
        sp_params.append(week_to)
    
    sp_where_clause = " AND ".join(sp_conditions)
    
    # Shipment Plans 데이터 조회
    shipment_plans = conn.execute(f'''
        SELECT from_site, to_site, model_name, shipping_week, shipping_quantity 
        FROM shipping_plans 
        WHERE {sp_where_clause}
    ''', sp_params).fetchall()
    
    # Purchase Orders 쿼리 조건 구성
    po_conditions = ["status = 'Active'"]
    po_params = []
    
    # Supplier 필터를 from_site로 적용
    if supplier_filter:
        po_conditions.append("from_site = ?")
        po_params.append(supplier_filter)
    
    # Week 범위를 날짜로 변환하여 SQL에서 직접 처리
    if week_from:
        po_conditions.append("rsd >= ?")
        po_params.append(week_from[:10])  # yyyy-mm-dd 부분만 추출
    
    if week_to:
        po_conditions.append("rsd <= ?")
        po_params.append(week_to[:10])   # yyyy-mm-dd 부분만 추출
    
    # Purchase Orders 데이터 조회 - try-except 제거
    purchase_orders = conn.execute(f'''
        SELECT po_number, from_site, to_site, model, po_qty, rsd, status 
        FROM purchase_orders 
        WHERE {" AND ".join(po_conditions)}
    ''', po_params).fetchall()
    
    conn.close()
    
    # 검색이 실행되었을 때 피벗 테이블 생성 (조건 유무와 관계없이)
    if search_executed:
        # 피벗 테이블 생성
        result = create_pivot_table(shipment_plans, purchase_orders)
        
        # 디버깅: 세부 데이터 확인
        print("=== DEBUGGING PIVOT DATA ===")
        for site, site_data in result['pivot_data'].items():
            print(f"Site: {site}")
            for week, week_data in site_data.items():
                sp_details = week_data.get('details', {}).get('sp', [])
                po_details = week_data.get('details', {}).get('po', [])
                print(f"  Week {week}: SP={len(sp_details)} records, PO={len(po_details)} records")
                if sp_details:
                    print(f"    SP Details: {sp_details[0]}")  # 첫 번째 레코드만 출력
                if po_details:
                    print(f"    PO Details: {po_details[0]}")  # 첫 번째 레코드만 출력
        print("=" * 50)
        
        return render_template('dashboard.html', 
                             pivot_data=result['pivot_data'],
                             weeks=result['weeks'],
                             week_totals=result['week_totals'],
                             grand_totals=result['grand_totals'],
                             overall_total=result['overall_total'],
                             suppliers=supplier_list,
                             search_executed=search_executed,
                             has_search_conditions=has_search_conditions)
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
                             has_search_conditions=has_search_conditions)

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
    cursor = conn.execute('''
        INSERT INTO shipping_plans (from_site, to_site, model_name, shipping_week, shipping_quantity, remark)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (from_site, to_site, model_name, shipping_week, shipping_quantity, remark))
    
    plan_id = cursor.lastrowid
    conn.commit()
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
    
    # 기존 데이터 조회
    old_data = conn.execute('SELECT * FROM shipping_plans WHERE id = ?', (id,)).fetchone()
    
    # 데이터 업데이트
    conn.execute('''
        UPDATE shipping_plans 
        SET from_site = ?, to_site = ?, model_name = ?, shipping_week = ?, shipping_quantity = ?, remark = ?, updated_at = (datetime(\'now\', \'localtime\'))
        WHERE id = ?
    ''', (from_site, to_site, model_name, shipping_week, shipping_quantity, remark, id))
    conn.commit()
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
    
    # 소프트 삭제 (삭제 시점도 updated_at에 기록)
    conn.execute('UPDATE shipping_plans SET is_deleted = TRUE, updated_at = (datetime(\'now\', \'localtime\')) WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    # 삭제는 is_deleted 필드로 추적 가능하므로 히스토리에 기록하지 않음
    
    return redirect(url_for('shipment'))

@app.route('/history/<int:id>')
def view_history(id):
    """특정 선적계획의 히스토리 조회"""
    conn = get_db_connection()
    
    # 계획 정보
    plan = conn.execute('SELECT * FROM shipping_plans WHERE id = ?', (id,)).fetchone()
    
    # 히스토리 정보
    history = conn.execute('''
        SELECT * FROM shipping_plans_history 
        WHERE plan_id = ? 
        ORDER BY changed_at DESC
    ''', (id,)).fetchall()
    
    conn.close()
    return render_template('history.html', plan=plan, history=history)

# Shipment page route
@app.route('/shipment')
def shipment():
    """Shipment page - Show shipping plans"""
    conn = get_db_connection()
    plans = conn.execute('''
        SELECT * FROM shipping_plans 
        WHERE is_deleted = FALSE 
        ORDER BY id DESC
    ''').fetchall()
    conn.close()
    return render_template('shipment.html', plans=plans)

# PO page route
@app.route('/po')
def po():
    """PO page - Show purchase orders"""
    conn = get_db_connection()
    pos = conn.execute('''
        SELECT * FROM purchase_orders 
        WHERE status = 'Active' 
        ORDER BY id DESC
    ''').fetchall()
    conn.close()
    return render_template('po.html', pos=pos)

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
    try:
        cursor = conn.execute('''
            INSERT INTO purchase_orders (po_number, from_site, to_site, model, po_qty, rsd, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (po_number, from_site, to_site, model, po_qty, rsd, remark))
        conn.commit()
    except sqlite3.IntegrityError as e:
        # 에러 발생 시에도 기존 PO 목록을 함께 전달
        pos = conn.execute('''
            SELECT * FROM purchase_orders 
            WHERE status = 'Active' 
            ORDER BY id DESC
        ''').fetchall()
        conn.close()
        
        if 'UNIQUE constraint failed' in str(e):
            return render_template('po.html', pos=pos, error='PO Number already exists! Please use a different PO number.')
        else:
            return render_template('po.html', pos=pos, error='Database error occurred.')
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
    
    # 기존 데이터 조회
    old_data = conn.execute('SELECT * FROM purchase_orders WHERE id = ?', (id,)).fetchone()
    
    # 데이터 업데이트
    conn.execute('''
        UPDATE purchase_orders 
        SET po_number = ?, from_site = ?, to_site = ?, model = ?, po_qty = ?, rsd = ?, remark = ?, 
            last_update = (datetime('now', 'localtime'))
        WHERE id = ?
    ''', (po_number, from_site, to_site, model, po_qty, rsd, remark, id))
    conn.commit()
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
    conn.execute('''
        UPDATE purchase_orders 
        SET status = 'Inactive', last_update = (datetime('now', 'localtime')) 
        WHERE id = ?
    ''', (id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('po'))

@app.route('/po_history/<int:id>')
def po_history(id):
    """View purchase order history"""
    conn = get_db_connection()
    
    # PO information
    po = conn.execute('SELECT * FROM purchase_orders WHERE id = ?', (id,)).fetchone()
    
    # PO history information
    history = conn.execute('''
        SELECT * FROM purchase_orders_history 
        WHERE po_id = ? 
        ORDER BY changed_at DESC
    ''', (id,)).fetchall()
    
    conn.close()
    return render_template('po_history.html', po=po, history=history)

@app.route('/api/plans')
def api_plans():
    """API: 선적계획 목록 JSON으로 반환"""
    conn = get_db_connection()
    plans = conn.execute('''
        SELECT * FROM shipping_plans 
        WHERE is_deleted = FALSE 
        ORDER BY id DESC
    ''').fetchall()
    conn.close()
    
    return jsonify([dict(row) for row in plans])

if __name__ == '__main__':
    
    app.run(debug=True, host='0.0.0.0', port=5000)