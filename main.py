from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import json
import requests

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
class AnalysisRequest(BaseModel):
    user_id: int
    summary_data: dict

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
# 5. OpenCodex AI 분석 생성 API (새로 추가)
@app.post("/api/analysis/generate")
def generate_ai_analysis(req: AnalysisRequest):
    # 1. AI에게 보낼 프롬프트 구성
    prompt = f"""
    당신은 전문 금융 자산 관리 AI 'Leið'입니다.
    사용자의 재무 데이터 요약: {req.summary_data}
    이 데이터를 바탕으로 다음 3가지 항목을 분석해 주세요. 
    반드시 HTML 태그(<strong>, <br>)를 사용하여 가독성 있게 작성하세요.
    1. [현재 금융 상태]
    2. [주요 이벤트 진단]
    3. [최종 제언]
    """
    
    # 2. OpenCodex API 호출 설정 (실제 해커톤에서 제공받은 URL과 키로 변경하세요)
    api_url = "https://api.opencodex.com/v1/chat/completions" # 예시 URL
    headers = {
        "Authorization": "Bearer 여기에_발급받은_API_키_입력", # 🚨 실제 키 입력
        "Content-Type": "application/json"
    }
    payload = {
        "model": "opencodex-model", # 🚨 실제 모델명 입력
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        # OpenCodex로 요청 보내기
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status() # 에러 발생 시 예외 처리
        
        # OpenCodex의 응답 텍스트 추출 (API 명세서에 따라 ['choices'][0] 등 구조가 다를 수 있음)
        result_text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "분석 결과를 불러올 수 없습니다.")
        
        return {"ai_analysis": result_text}
        
    except Exception as e:
        print("AI 호출 에러:", e)
        # API 연결 실패 시 예외 처리용 임시 텍스트
        fallback_text = "<strong>[시스템 안내]</strong><br>현재 OpenCodex AI 서버와 통신할 수 없습니다. API 키 및 네트워크 상태를 확인해 주세요."
        return {"ai_analysis": fallback_text}