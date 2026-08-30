from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import json

app = FastAPI(title="Leið Backend Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🚨 기존 DB와의 충돌을 막기 위해 새 데이터베이스 파일(leid2.db) 생성
DB_FILE = "leid2.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # login_id와 email을 완벽히 분리
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login_id TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            birthdate TEXT NOT NULL,
            job TEXT
        )
    """)
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

class SignupRequest(BaseModel):
    login_id: str
    email: str
    password: str
    name: str
    birthdate: str
    job: Optional[str] = ""

class LoginRequest(BaseModel):
    login_id: str
    password: str

class FinancialItem(BaseModel):
    name: Optional[str] = ""
    amount: Optional[int] = 0
    kind: Optional[str] = "asset"
    rate: Optional[str] = ""

class EventItem(BaseModel):
    name: Optional[str] = ""
    year: Optional[int] = 0
    amount: Optional[int] = 0

class SaveDataRequest(BaseModel):
    user_id: int
    financial_items: Optional[List[FinancialItem]] = []
    events: Optional[List[EventItem]] = []

@app.get("/api/auth/check-id")
def check_id(login_id: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE login_id = ?", (login_id,))
    record = cursor.fetchone()
    conn.close()
    if record:
        raise HTTPException(status_code=400, detail="이미 사용 중인 아이디입니다.")
    return {"message": "사용 가능한 아이디입니다."}

@app.post("/api/auth/signup")
def signup(req: SignupRequest):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE login_id = ?", (req.login_id,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="이미 사용 중인 아이디입니다.")
    
    cursor.execute("""
        INSERT INTO users (login_id, email, password, name, birthdate, job)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (req.login_id, req.email, req.password, req.name, req.birthdate, req.job))
    conn.commit()
    conn.close()
    return {"message": "회원가입이 완료되었습니다."}

@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name FROM users 
        WHERE login_id = ? AND password = ?
    """, (req.login_id, req.password))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 일치하지 않습니다.")
    
    return {"message": "로그인 성공", "user": {"id": user[0], "name": user[1]}}

@app.post("/api/data/save")
def save_data(req: SaveDataRequest):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    finance_json = json.dumps([item.dict() for item in req.financial_items], ensure_ascii=False)
    events_json = json.dumps([item.dict() for item in req.events], ensure_ascii=False)
    
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

@app.get("/api/data/load")
def load_data(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT finance_json, events_json FROM financial_data WHERE user_id = ?", (user_id,))
    record = cursor.fetchone()
    conn.close()
    if not record:
        return {"message": "저장된 데이터가 없습니다.", "financial_items": [], "events": []}
    return {"message": "데이터 불러오기 성공", "financial_items": json.loads(record[0]), "events": json.loads(record[1])}