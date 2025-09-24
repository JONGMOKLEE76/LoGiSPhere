from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)

def get_db_connection():
    """데이터베이스 연결"""
    conn = sqlite3.connect('shipping_plan.db')
    conn.row_factory = sqlite3.Row
    return conn

def log_history(plan_id, action_type, field_name=None, old_value=None, new_value=None):
    """히스토리 로그 기록"""
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO shipping_plans_history (plan_id, action_type, field_name, old_value, new_value)
        VALUES (?, ?, ?, ?, ?)
    ''', (plan_id, action_type, field_name, old_value, new_value))
    conn.commit()
    conn.close()

@app.route('/')
def index():
    """메인 페이지 - 선적계획 목록 표시"""
    conn = get_db_connection()
    plans = conn.execute('''
        SELECT * FROM shipping_plans 
        WHERE is_deleted = FALSE 
        ORDER BY id DESC
    ''').fetchall()
    conn.close()
    return render_template('index.html', plans=plans)

@app.route('/add', methods=['POST'])
def add_plan():
    """새로운 선적계획 추가"""
    company_name = request.form['company_name']
    to_site = request.form['to_site']
    model_name = request.form['model_name']
    shipping_week = request.form['shipping_week']
    shipping_quantity = int(request.form['shipping_quantity'])
    
    conn = get_db_connection()
    cursor = conn.execute('''
        INSERT INTO shipping_plans (company_name, to_site, model_name, shipping_week, shipping_quantity)
        VALUES (?, ?, ?, ?, ?)
    ''', (company_name, to_site, model_name, shipping_week, shipping_quantity))
    
    plan_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # 생성은 created_at으로 추적 가능하므로 히스토리에 기록하지 않음
    
    return redirect(url_for('index'))

@app.route('/update/<int:id>', methods=['POST'])
def update_plan(id):
    """선적계획 수정"""
    company_name = request.form['company_name']
    to_site = request.form['to_site']
    model_name = request.form['model_name']
    shipping_week = request.form['shipping_week']
    shipping_quantity = int(request.form['shipping_quantity'])
    
    conn = get_db_connection()
    
    # 기존 데이터 조회
    old_data = conn.execute('SELECT * FROM shipping_plans WHERE id = ?', (id,)).fetchone()
    
    # 데이터 업데이트
    conn.execute('''
        UPDATE shipping_plans 
        SET company_name = ?, to_site = ?, model_name = ?, shipping_week = ?, shipping_quantity = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (company_name, to_site, model_name, shipping_week, shipping_quantity, id))
    conn.commit()
    conn.close()
    
    # 변경된 필드 히스토리 기록
    if old_data['company_name'] != company_name:
        log_history(id, 'UPDATE', 'company_name', old_data['company_name'], company_name)
    if old_data['to_site'] != to_site:
        log_history(id, 'UPDATE', 'to_site', old_data['to_site'], to_site)
    if old_data['model_name'] != model_name:
        log_history(id, 'UPDATE', 'model_name', old_data['model_name'], model_name)
    if old_data['shipping_week'] != shipping_week:
        log_history(id, 'UPDATE', 'shipping_week', old_data['shipping_week'], shipping_week)
    if old_data['shipping_quantity'] != shipping_quantity:
        log_history(id, 'UPDATE', 'shipping_quantity', str(old_data['shipping_quantity']), str(shipping_quantity))
    
    return redirect(url_for('index'))

@app.route('/delete/<int:id>', methods=['POST'])
def delete_plan(id):
    """선적계획 삭제 (소프트 삭제)"""
    conn = get_db_connection()
    
    # 소프트 삭제
    conn.execute('UPDATE shipping_plans SET is_deleted = TRUE WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    # 삭제는 is_deleted 필드로 추적 가능하므로 히스토리에 기록하지 않음
    
    return redirect(url_for('index'))

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
    # 데이터베이스 초기화
    if not os.path.exists('shipping_plan.db'):
        from init_db import init_database
        init_database()
    
    app.run(debug=True, host='0.0.0.0', port=5000)