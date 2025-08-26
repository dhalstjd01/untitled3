# C:/Users/zxzx0/Desktop/chatbot/AIChatBot/AIchat/init_db.py

import sqlite3

conn = sqlite3.connect('chatbot_likes.db')
cursor = conn.cursor()

# 1. '좋아요' 테이블 (변경 없음)
cursor.execute('''
               CREATE TABLE IF NOT EXISTS liked_messages (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER NOT NULL,
                   bot_type TEXT NOT NULL,
                   message TEXT NOT NULL,
                   liked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
               )
               ''')

# 2. 대화 세션 테이블 (변경 없음)
cursor.execute('''
               CREATE TABLE IF NOT EXISTS chat_sessions (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER NOT NULL,
                   bot_type TEXT NOT NULL,
                   history_json TEXT NOT NULL,
                   phq_completed INTEGER NOT NULL DEFAULT 0,
                   user_stage INTEGER NOT NULL DEFAULT 1,
                   session_name TEXT,
                   is_active INTEGER NOT NULL DEFAULT 1,
                   emotion_summary_json TEXT DEFAULT '{}',
                   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
               )
               ''')

# 3. ✨ [추가] 모든 감정 분석 결과를 기록할 테이블
cursor.execute('''
               CREATE TABLE IF NOT EXISTS emotion_logs (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   session_id INTEGER NOT NULL,
                   user_id INTEGER NOT NULL,
                   bot_type TEXT NOT NULL,
                   emotion TEXT NOT NULL,
                   analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                   FOREIGN KEY (session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
               )
               ''')


print("✅ 데이터베이스가 'emotion_logs' 테이블을 포함한 최신 구조로 생성되었습니다.")

conn.commit()
conn.close()