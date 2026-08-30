from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import json
import requests
import os

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
# 5. Gemini AI 분석 생성 API (무료)
@app.post("/api/analysis/generate")
def generate_ai_analysis(req: AnalysisRequest):
    prompt = f"""
    당신은 사용자 입력 데이터만으로 팩트를 짚어주는 냉철한 금융 AI 'Leið'입니다.
    사용자의 재무 데이터 요약: {req.summary_data}
    
    [절대 원칙]
    1. 제공된 데이터 외의 수치(부족액, DSR 등)를 임의로 창작하거나 계산하지 마십시오.
    2. "위기", "심각", "타격" 등의 감정적 단어를 배제하고 객관적 상태만 서술하십시오.
    3. 모바일 UI에 맞게 전체 내용을 공백 포함 300자 이내로 극단적으로 요약하십시오.
    
    아래 3가지 항목으로 나누어 HTML 태그(<strong>, <br>)를 사용해 출력하십시오.
    
    <strong>[현재 상태 요약]</strong><br>
    (현재 순자산과 연간 여유자금 구조가 긍정적인지 부정적인지 1~2문장으로 팩트만 서술)
    <br><br>
    <strong>[위험 이벤트 진단]</strong><br>
    (가장 점수가 낮은 해의 이벤트를 지목하고 원인을 서술. 하락 구간이 없다면 평탄하다고 서술)
    <br><br>
    <strong>[핵심 조정 제언]</strong><br>
    (이벤트 시점 연기, 지출 축소 등 사용자가 당장 실행 가능한 현실적인 행동 1가지만 제시)
    """
    
    # 🚨 발급받은 Gemini API 키를 아래 빈칸에 붙여넣으세요!
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    
    # Gemini 1.5 Flash 모델 REST API 엔드포인트
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Gemini 규격에 맞춘 페이로드 구조
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    try:
        # Gemini 서버로 데이터 전송 및 답변 대기
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status() 
        
        # Gemini가 보내준 답변 텍스트만 정확하게 추출
        result_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        
        return {"ai_analysis": result_text}
        
    except Exception as e:
        print("AI 호출 에러:", e)
        fallback_text = "<strong>[시스템 안내]</strong><br>현재 AI 서버와 통신할 수 없습니다. API 키 상태를 확인해 주세요."
        return {"ai_analysis": fallback_text}