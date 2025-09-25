# 선적계획 DB 변경관리 시스템

Flask와 SQLite3를 기반으로 구축된 **선적계획 데이터베이스 히스토리 관리 웹 애플리케이션**입니다.

## 📋 **프로젝트 개요**

물류/선적 업무에서 데이터의 변경 이력을 체계적으로 관리하고 추적할 수 있는 완전한 웹 애플리케이션입니다.

## 🚀 **주요 기능**

### 1. **선적계획 데이터 관리 (CRUD)**
- 업체명, 선적지, 선적주차, 선적수량 정보 관리
- 웹 인터페이스를 통한 직관적인 데이터 입력/수정
- 실시간 데이터 수정 기능

### 2. **변경이력 추적 시스템**
- 모든 데이터 변경사항을 자동으로 기록
- 필드별 변경 내역 상세 추적
- 소프트 삭제로 데이터 보존

### 3. **대시보드 및 리포팅**
- 실시간 데이터 현황 조회
- 히스토리 페이지에서 변경 이력 확인
- PO(구매 주문) 관리 기능

## 📊 **선적계획 데이터 구조**

1. **업체명** - 선적을 진행하는 업체의 이름
2. **선적지 (To Site)** - 물품이 선적될 목적지
3. **선적주차** - 선적이 예정된 주차 (예: 2025-09-22(W39))
4. **선적수량** - 선적될 물품의 수량

## 🛠 **기술 스택**

- **Backend**: Flask (Python)
- **Database**: SQLite3
- **Frontend**: HTML, CSS, JavaScript
- **템플릿 엔진**: Jinja2

## 🎯 **핵심 특징**

- **변경 이력 자동 추적**: 모든 데이터 변경사항이 자동으로 기록됨
- **소프트 삭제**: 데이터를 완전히 삭제하지 않고 플래그로 관리
- **주차 형식 자동 변환**: 날짜를 주차 형식으로 자동 변환
- **RESTful API**: JSON 형태의 API 엔드포인트 제공

## 설치 및 실행

### 1. 가상환경 생성 및 활성화

```bash
# 가상환경 생성
python -m venv venv

# 가상환경 활성화 (Windows)
venv\Scripts\activate

# 가상환경 활성화 (macOS/Linux)
source venv/bin/activate
```

### 2. 의존성 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. 데이터베이스 초기화

```bash
python init_db.py
```

### 4. 애플리케이션 실행

```bash
python app.py
```

웹 브라우저에서 `http://localhost:5000` 접속

## 📁 **프로젝트 구조**

```
DB_Change_History/
├── app.py                 # Flask 메인 애플리케이션
├── init_db.py            # 데이터베이스 초기화
├── create_po_table.py    # PO 테이블 생성 스크립트
├── requirements.txt      # 의존성 패키지
├── static/
│   └── style.css        # 스타일시트
└── templates/           # HTML 템플릿들
    ├── dashboard.html   # 대시보드
    ├── history.html     # 변경 이력
    ├── index.html       # 메인 페이지
    ├── po_history.html  # PO 히스토리
    ├── po.html          # PO 관리
    └── shipment.html    # 선적 관리
```

## 💾 **데이터베이스 설계**

### 1. **shipping_plans 테이블** - 선적계획 메인 데이터
- `id`: 기본키 (자동증가)
- `from_site`: 업체명
- `to_site`: 선적지
- `shipping_week`: 선적주차
- `shipping_quantity`: 선적수량
- `created_at`: 생성일시
- `updated_at`: 수정일시
- `is_deleted`: 삭제 여부 (소프트 삭제)

### 2. **shipping_plans_history 테이블** - 변경 이력 추적
- `history_id`: 히스토리 기본키
- `plan_id`: 선적계획 ID (외래키)
- `action_type`: 작업 유형 (INSERT, UPDATE, DELETE)
- `field_name`: 변경된 필드명
- `old_value`: 이전 값
- `new_value`: 새로운 값
- `changed_at`: 변경일시

### 3. **purchase_orders 테이블** - 구매 주문 관리
- PO 번호, 업체명, 수량 등 구매 주문 정보

### 4. **po_history 테이블** - PO 변경 이력
- PO 데이터의 모든 변경사항 추적

## 사용법

1. **새 선적계획 추가**: 상단의 입력 폼을 사용하여 새로운 선적계획을 추가할 수 있습니다.

2. **데이터 수정**: 각 행의 "수정" 버튼을 클릭하여 인라인으로 데이터를 수정할 수 있습니다.

3. **히스토리 조회**: "히스토리" 버튼을 클릭하여 해당 레코드의 모든 변경 이력을 확인할 수 있습니다.

4. **데이터 삭제**: "삭제" 버튼을 클릭하여 데이터를 삭제할 수 있습니다. (소프트 삭제로 히스토리는 보존됩니다)

## 🌐 **API 엔드포인트**

### 선적계획 관리
- `GET /`: 메인 페이지
- `POST /add`: 새 선적계획 추가
- `POST /update/<id>`: 선적계획 수정
- `POST /delete/<id>`: 선적계획 삭제
- `GET /history/<id>`: 히스토리 조회
- `GET /api/plans`: JSON 형태의 선적계획 목록 API

### 대시보드 및 기타
- `GET /dashboard`: 대시보드 페이지
- `GET /shipment`: 선적 관리 페이지
- `GET /po`: PO 관리 페이지
- `GET /po_history/<id>`: PO 히스토리 조회

## 개발 환경

- Python 3.7+
- Flask 2.3.3
- SQLite3 (Python 내장)

## 라이선스

MIT License