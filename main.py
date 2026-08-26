from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import json

app = FastAPI(title="Leið Backend Server")

# 브라우저(HTML)와 서버 간의 통신을 허용하는 CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------
# 데이터베이스 초기화 (SQLite)
# -------------------------------------------------------------
def init_db():
    conn = sqlite3.connect("leid.db")
    cursor = conn.cursor()
    
    # 유저 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_or_phone TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            birthdate TEXT NOT NULL,
            job TEXT
        )
    """)
    
    # 금융 데이터 저장 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            finance_json TEXT NOT NULL,
            events_json TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------
# 요청 데이터 스키마 정의 (Pydantic)
# -------------------------------------------------------------
class SignupRequest(BaseModel):
    name: str
    birthdate: str
    email_or_phone: str
    password: str
    job: Optional[str] = ""

class LoginRequest(BaseModel):
    email_or_phone: str
    password: str

class FinancialItem(BaseModel):
    name: Optional[str] = ""
    amount: Optional[int] = 0

class EventItem(BaseModel):
    name: Optional[str] = ""
    year: Optional[int] = 0
    amount: Optional[int] = 0

class SaveDataRequest(BaseModel):
    user_id: int
    financial_items: Optional[List[FinancialItem]] = []
    events: Optional[List[EventItem]] = []

# -------------------------------------------------------------
# API 엔드포인트
# -------------------------------------------------------------

# 1. 회원가입 API
@app.post("/api/auth/signup")
def signup(req: SignupRequest):
    conn = sqlite3.connect("leid.db")
    cursor = conn.cursor()
    
    # 중복 계정 확인
    cursor.execute("SELECT id FROM users WHERE email_or_phone = ?", (req.email_or_phone,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="이미 등록된 이메일 또는 전화번호입니다.")
    
    cursor.execute("""
        INSERT INTO users (email_or_phone, password, name, birthdate, job)
        VALUES (?, ?, ?, ?, ?)
    """, (req.email_or_phone, req.password, req.name, req.birthdate, req.job))
    
    conn.commit()
    conn.close()
    return {"message": "회원가입이 완료되었습니다."}

# 2. 로그인 API
@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = sqlite3.connect("leid.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name FROM users 
        WHERE email_or_phone = ? AND password = ?
    """, (req.email_or_phone, req.password))
    
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="아이디(이메일/연락처) 또는 비밀번호가 일치하지 않습니다.")
    
    return {
        "message": "로그인 성공",
        "user": {
            "id": user[0],
            "name": user[1]
        }
    }

# 3. 금융 데이터 저장 API
@app.post("/api/data/save")
def save_data(req: SaveDataRequest):
    conn = sqlite3.connect("leid.db")
    cursor = conn.cursor()
    
    finance_json = json.dumps([item.dict() for item in req.financial_items], ensure_ascii=False)
    events_json = json.dumps([item.dict() for item in req.events], ensure_ascii=False)
    
    # 기존 저장 내역 확인 후 덮어쓰기/신규 생성
    cursor.execute("SELECT id FROM financial_data WHERE user_id = ?", (req.user_id,))
    record = cursor.fetchone()
    
    if record:
        cursor.execute("""
            UPDATE financial_data 
            SET finance_json = ?, events_json = ?
            WHERE user_id = ?
        """, (finance_json, events_json, req.user_id))
    else:
        cursor.execute("""
            INSERT INTO financial_data (user_id, finance_json, events_json)
            VALUES (?, ?, ?)
        """, (req.user_id, finance_json, events_json))
        
    conn.commit()
    conn.close()
    return {"message": "데이터가 성공적으로 저장되었습니다."}