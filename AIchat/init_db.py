# C:/.../AIchat/init_db.py

import sqlite3

# 데이터베이스 연결 (파일이 없으면 새로 생성됨)
conn = sqlite3.connect('chatbot_likes.db')
cursor = conn.cursor()

# 1. 사용자 정보 테이블
cursor.execute('''
               CREATE TABLE IF NOT EXISTS users (
                                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                    username TEXT NOT NULL UNIQUE
               )
               ''')

# 2. 대화 '세션' 정보 저장 테이블
# ⭐ [수정] 대화형 설문 진행 상태를 위한 phq_progress와 phq_scores 컬럼 추가
cursor.execute('''
               CREATE TABLE IF NOT EXISTS chat_sessions (
                                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                            user_id INTEGER NOT NULL,
                                                            bot_type TEXT NOT NULL,
                                                            phq_completed INTEGER NOT NULL DEFAULT 0,
                                                            user_stage TEXT DEFAULT '1',
                                                            session_name TEXT,
                                                            last_phq_timestamp REAL,
                                                            next_phq_eligible_timestamp REAL,
                                                            phq_progress INTEGER DEFAULT -1,
                                                            phq_scores TEXT,
                                                            is_active INTEGER NOT NULL DEFAULT 1,
                                                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                            FOREIGN KEY (user_id) REFERENCES users (id)
                   )
               ''')

# 3. 모든 '메시지'와 '감정'을 개별적으로 저장하는 테이블
cursor.execute('''
               CREATE TABLE IF NOT EXISTS messages (
                                                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                       session_id INTEGER NOT NULL,
                                                       role TEXT NOT NULL, -- 'user' or 'assistant'
                                                       content TEXT NOT NULL,
                                                       emotion TEXT, -- 사용자의 메시지에만 기록됨
                                                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                                       FOREIGN KEY (session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
                   )
               ''')

# 4. '좋아요' 누른 메시지 저장 테이블
cursor.execute('''
               CREATE TABLE IF NOT EXISTS liked_messages (
                                                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                             user_id INTEGER NOT NULL,
                                                             bot_type TEXT NOT NULL,
                                                             message TEXT NOT NULL,
                                                             liked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
               )
               ''')

# 기본 사용자 추가 (최초 1회 실행)
try:
    cursor.execute("INSERT INTO users (id, username) VALUES (1, '홍길동')")
    print("✅ 기본 사용자(홍길동)가 추가되었습니다.")
except sqlite3.IntegrityError:
    print("ℹ️ 기본 사용자가 이미 존재합니다. (정상적인 동작입니다)")


print("✅ 데이터베이스 및 모든 테이블이 새로운 구조로 생성되었습니다.")

conn.commit()
conn.close()