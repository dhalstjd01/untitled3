# C:/Users/3014m/Downloads/AIChatBot (2)/untitled3/AIchat/app.py

import random
import sqlite3
import json
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from chatbot import Chatbot
from prompts import (
    PERSONA_HO_PROMPT, PERSONA_UNG_PROMPT,
    GREETINGS_HO, GREETINGS_UNG,
    PHQ9_QUESTIONS, SCENARIOS
)

load_dotenv()
app = Flask(__name__)
app.secret_key = 'your-very-secret-key-for-aichat'

# 챗봇 인스턴스는 한 번만 생성하여 재사용합니다.
try:
    chatbot_instance = Chatbot()
except Exception as e:
    print(f"❌ Chatbot 인스턴스 생성 실패: {e}")
    chatbot_instance = None

def get_db_conn():
    """데이터베이스 연결 객체를 반환하는 함수"""
    conn = sqlite3.connect('chatbot_likes.db')
    conn.row_factory = sqlite3.Row
    return conn

PERSONAS = {
    "ho": { "name": "호", "prompt": PERSONA_HO_PROMPT, "profile_image": "/static/images/profile_ho.png", "greetings": GREETINGS_HO },
    "ung": { "name": "웅", "prompt": PERSONA_UNG_PROMPT, "profile_image": "/static/images/profile_ung.png", "greetings": GREETINGS_UNG }
}

def get_stage_from_score(score):
    """PHQ-9 점수에 따라 사용자 단계를 반환하는 함수"""
    if score <= 4: return 1
    if score <= 9: return 2
    if score <= 19: return 3
    return 4

@app.route("/")
def index():
    """메인 페이지. 데모를 위해 user_id=1로 자동 로그인합니다."""
    # 실제 서비스에서는 로그인 로직이 필요합니다.
    session['user_id'] = 1
    session['username'] = '홍길동'
    return render_template("index.html")

@app.route("/chat/<bot_type>")
def chat(bot_type):
    """
    채팅 페이지를 렌더링합니다.
    다른 페이지에 다녀와도 대화가 초기화되지 않도록 로직을 강화했습니다.
    """
    if 'user_id' not in session:
        return "로그인이 필요합니다.", 401

    persona = PERSONAS.get(bot_type)
    if not persona:
        return "챗봇을 찾을 수 없습니다.", 404

    user_id = session['user_id']
    conn = get_db_conn()
    try:
        # 1. 현재 활성(active) 세션을 찾습니다.
        active_session = conn.execute(
            'SELECT * FROM chat_sessions WHERE user_id = ? AND bot_type = ? AND is_active = 1',
            (user_id, bot_type)
        ).fetchone()

        # 2. 활성 세션이 없다면, 가장 최근 세션을 찾아 활성화합니다. (대화 유지의 핵심)
        if not active_session:
            latest_session = conn.execute(
                'SELECT * FROM chat_sessions WHERE user_id = ? AND bot_type = ? ORDER BY created_at DESC LIMIT 1',
                (user_id, bot_type)
            ).fetchone()
            if latest_session:
                conn.execute('UPDATE chat_sessions SET is_active = 1 WHERE id = ?', (latest_session['id'],))
                conn.commit()
                active_session = conn.execute('SELECT * FROM chat_sessions WHERE id = ?', (latest_session['id'],)).fetchone()

        initial_history = []
        if active_session:
            # 3. 활성 세션이 있으면, messages 테이블에서 모든 메시지를 불러옵니다.
            messages = conn.execute(
                'SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC',
                (active_session['id'],)
            ).fetchall()
            initial_history = [dict(m) for m in messages]
        else:
            # 4. 어떤 세션도 없다면 (최초 대화), 새로운 세션을 생성합니다.
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO chat_sessions (user_id, bot_type, session_name) VALUES (?, ?, ?)",
                (user_id, bot_type, "새로운 대화")
            )
            new_session_id = cursor.lastrowid
            welcome_message = random.choice(persona["greetings"])
            initial_history = [{"role": "assistant", "content": welcome_message}]
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (new_session_id, "assistant", welcome_message)
            )
            conn.commit()
    finally:
        conn.close()

    return render_template(
        "chat.html",
        bot_name=persona["name"],
        bot_type=bot_type,
        profile_image=persona["profile_image"],
        initial_history=json.dumps(initial_history, ensure_ascii=False)
    )

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """사용자 메시지를 받고 챗봇 응답을 반환하는 API (PHQ-9 로직 포함)"""
    if 'user_id' not in session:
        return jsonify({"error": "로그인이 필요합니다."}), 401

    data = request.json
    user_message = data.get("message", "").strip()
    bot_type = data.get("bot_type")
    user_id = session['user_id']

    if not user_message or not bot_type:
        return jsonify({"error": "필수 정보가 누락되었습니다."}), 400

    if not chatbot_instance:
        return jsonify({"error": "챗봇 서비스가 초기화되지 않았습니다."}), 503

    conn = get_db_conn()
    try:
        active_session = conn.execute(
            'SELECT * FROM chat_sessions WHERE user_id = ? AND bot_type = ? AND is_active = 1',
            (user_id, bot_type)
        ).fetchone()
        if not active_session:
            return jsonify({"error": "활성 채팅 세션을 찾을 수 없습니다."}), 404

        session_id = active_session['id']

        # 1. 사용자 메시지를 DB에 먼저 저장
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, 'user', user_message)
        )
        last_message_id = cursor.lastrowid
        conn.commit()

        # 2. 최신 대화 기록을 DB에서 다시 불러옴
        history_rows = conn.execute(
            'SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC', (session_id,)
        ).fetchall()
        history = [dict(row) for row in history_rows]

        bot_response = None
        phq_completed = bool(active_session['phq_completed'])
        user_stage = active_session['user_stage']

        # --- [수정] PHQ-9 설문 로직 ---
        if not phq_completed:
            is_numeric_answer = user_message in ["1", "2", "3", "4"]
            phq_answers_in_db = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user' AND content IN ('1', '2', '3', '4')",
                (session_id,)
            ).fetchone()[0]

            # 첫 번째 사용자 메시지일 경우
            if sum(1 for msg in history if msg['role'] == 'user') == 1:
                question_text = PHQ9_QUESTIONS[0]['question']
                options_text = "\n\n(답변: 1. 전혀 없음 / 2. 며칠 동안 / 3. 일주일 이상 / 4. 거의 매일)"
                bot_response = f"이야기를 시작하기 전에, 잠시 당신의 마음 상태를 점검해볼게요.\n\n{question_text}{options_text}"
            # 숫자 답변이 아닌데 질문이 진행중인 경우
            elif not is_numeric_answer and phq_answers_in_db > 0:
                bot_response = "앗, 1, 2, 3, 4 중 하나의 숫자로만 골라줄 수 있을까?"
                conn.execute("DELETE FROM messages WHERE id = ?", (last_message_id,))
                conn.commit()
            # 숫자 답변을 받았을 경우
            elif is_numeric_answer:
                current_q_index = phq_answers_in_db
                if current_q_index < len(PHQ9_QUESTIONS):
                    next_question_data = PHQ9_QUESTIONS[current_q_index]
                    bot_response = f"{next_question_data['question']}\n\n(답변: 1. 전혀 없음 / 2. 며칠 동안 / 3. 일주일 이상 / 4. 거의 매일)"
                else: # 모든 질문에 답변 완료
                    answer_rows = conn.execute(
                        "SELECT content FROM messages WHERE session_id = ? AND role = 'user' AND content IN ('1', '2', '3', '4')",
                        (session_id,)
                    ).fetchall()
                    answers = [row['content'] for row in answer_rows]
                    score = sum(PHQ9_QUESTIONS[i]['options'][ans] for i, ans in enumerate(answers))
                    user_stage = get_stage_from_score(score)
                    conn.execute('UPDATE chat_sessions SET user_stage = ?, phq_completed = ? WHERE id = ?', (user_stage, 1, session_id))
                    bot_response = "마음 점검이 완료되었습니다. 이야기 나눠주셔서 감사해요. 이제 편하게 당신의 이야기를 들려주세요."

        # --- 일반 대화 및 감정 분석 로직 ---
        if bot_response is None:
            bot_response, detected_emotion = chatbot_instance.get_response_and_emotion(
                user_input=user_message,
                persona_prompt=PERSONAS[bot_type]["prompt"],
                history=history,
                stage=user_stage
            )
            if detected_emotion != "분석실패":
                conn.execute('UPDATE messages SET emotion = ? WHERE id = ?', (detected_emotion, last_message_id))

        # 3. 봇 응답을 DB에 저장
        conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, 'assistant', bot_response)
        )

        # 4. 세션 이름 업데이트 (최초 1회)
        if active_session['session_name'] == "새로운 대화":
            conn.execute('UPDATE chat_sessions SET session_name = ? WHERE id = ?', (user_message[:50], session_id))

        conn.commit()
        return jsonify({"response": bot_response})

    except Exception as e:
        print(f"Error in /api/chat: {e}")
        conn.rollback()
        return jsonify({"error": "서버 처리 중 오류가 발생했습니다."}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/new_chat", methods=["POST"])
def new_chat():
    """새로운 대화를 시작하는 API"""
    user_id = session['user_id']
    bot_type = request.json.get('bot_type')
    conn = get_db_conn()
    try:
        conn.execute('UPDATE chat_sessions SET is_active = 0 WHERE user_id = ? AND bot_type = ? AND is_active = 1', (user_id, bot_type))

        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_sessions (user_id, bot_type, session_name) VALUES (?, ?, ?)",
            (user_id, bot_type, "새로운 대화")
        )
        new_session_id = cursor.lastrowid

        welcome_message = random.choice(PERSONAS[bot_type]["greetings"])
        new_history = [{"role": "assistant", "content": welcome_message}]
        conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (new_session_id, "assistant", welcome_message)
        )
        conn.commit()
        return jsonify({"history": new_history})
    except Exception as e:
        print(f"Error in /api/new_chat: {e}")
        conn.rollback()
        return jsonify({"error": "새 대화 생성 중 오류 발생"}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/past_chats", methods=["GET"])
def get_past_chats():
    """과거 대화 목록을 반환하는 API"""
    user_id = session['user_id']
    bot_type = request.args.get('bot_type')
    conn = get_db_conn()
    try:
        past_chats = conn.execute(
            'SELECT id, session_name, created_at FROM chat_sessions WHERE user_id = ? AND bot_type = ? AND is_active = 0 ORDER BY created_at DESC',
            (user_id, bot_type)
        ).fetchall()
        return jsonify([dict(row) for row in past_chats])
    finally:
        if conn:
            conn.close()

@app.route("/api/load_chat", methods=["POST"])
def load_chat():
    """과거 대화를 불러오는 API"""
    user_id = session['user_id']
    bot_type = request.json.get('bot_type')
    session_id_to_load = request.json.get('session_id')
    conn = get_db_conn()
    try:
        conn.execute('UPDATE chat_sessions SET is_active = 0 WHERE user_id = ? AND bot_type = ?', (user_id, bot_type))
        conn.execute('UPDATE chat_sessions SET is_active = 1 WHERE id = ? AND user_id = ?', (session_id_to_load, user_id))

        loaded_messages = conn.execute('SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC', (session_id_to_load,)).fetchall()
        conn.commit()

        return jsonify({"history": [dict(m) for m in loaded_messages]})
    except Exception as e:
        print(f"Error in /api/load_chat: {e}")
        conn.rollback()
        return jsonify({"error": "대화 불러오기 중 오류 발생"}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/delete_session", methods=["POST"])
def delete_session():
    """대화 세션을 삭제하는 API (관련 메시지도 함께 삭제됨)"""
    user_id = session['user_id']
    session_id = request.json.get('session_id')
    conn = get_db_conn()
    try:
        # ON DELETE CASCADE 덕분에 chat_sessions에서만 삭제해도 messages가 함께 삭제됨
        cursor = conn.execute('DELETE FROM chat_sessions WHERE id = ? AND user_id = ?', (session_id, user_id))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"status": "error", "message": "삭제 권한이 없거나 세션을 찾을 수 없습니다."}), 404
        return jsonify({"status": "success", "message": "대화가 삭제되었습니다."})
    except Exception as e:
        print(f"Error in /api/delete_session: {e}")
        conn.rollback()
        return jsonify({"error": "대화 삭제 중 오류 발생"}), 500
    finally:
        if conn:
            conn.close()

@app.route("/analysis/<bot_type>")
def analysis(bot_type):
    """감정 분석 그래프 페이지 (messages 테이블에서 직접 데이터 집계)"""
    if 'user_id' not in session:
        return "로그인이 필요합니다.", 401

    persona = PERSONAS.get(bot_type)
    if not persona:
        return "챗봇을 찾을 수 없습니다.", 404

    user_id = session['user_id']
    conn = get_db_conn()
    try:
        active_session = conn.execute(
            'SELECT id FROM chat_sessions WHERE user_id = ? AND bot_type = ? AND is_active = 1',
            (user_id, bot_type)
        ).fetchone()

        emotion_data = {}
        if active_session:
            emotion_rows = conn.execute(
                'SELECT emotion, COUNT(*) as count FROM messages WHERE session_id = ? AND emotion IS NOT NULL GROUP BY emotion',
                (active_session['id'],)
            ).fetchall()
            emotion_data = {row['emotion']: row['count'] for row in emotion_rows}
    finally:
        if conn:
            conn.close()

    return render_template(
        "analysis.html",
        bot_name=persona["name"],
        bot_type=bot_type,
        emotion_data=emotion_data
    )

# --- '저장한 문구' 관련 라우트들 ---

@app.route("/api/like_message", methods=["POST"])
def like_message():
    if 'user_id' not in session: return jsonify({"status": "error", "message": "로그인이 필요합니다."}), 401
    data = request.json
    conn = get_db_conn()
    try:
        conn.execute('INSERT INTO liked_messages (user_id, bot_type, message) VALUES (?, ?, ?)',
                     (session['user_id'], data.get("bot_type"), data.get("message")))
        conn.commit()
        return jsonify({"status": "success", "message": "메시지를 저장했습니다."})
    except Exception as e:
        print(f"Error in /api/like_message: {e}")
        conn.rollback()
        return jsonify({"status": "error", "message": "메시지 저장 중 오류 발생"})
    finally:
        if conn:
            conn.close()

@app.route("/favorites")
def favorites():
    if 'user_id' not in session:
        return "로그인이 필요합니다.", 401
    return render_template("favorites.html")

@app.route("/api/favorites", methods=["GET"])
def get_favorites():
    if 'user_id' not in session:
        return jsonify({"error": "로그인이 필요합니다."}), 401
    conn = get_db_conn()
    try:
        messages = conn.execute('''
                                SELECT id, bot_type, message, liked_at,
                                       CASE bot_type WHEN 'ho' THEN '호' WHEN 'ung' THEN '웅' ELSE '알 수 없음' END as bot_name
                                FROM liked_messages WHERE user_id = ? ORDER BY liked_at DESC
                                ''', (session['user_id'],)).fetchall()
        return jsonify([dict(row) for row in messages])
    except Exception as e:
        print(f"Error in /api/favorites: {e}")
        return jsonify({"error": "데이터를 불러오는 중 오류가 발생했습니다."}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/delete_favorite", methods=["POST"])
def delete_favorite():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "로그인이 필요합니다."}), 401
    data = request.json
    message_id = data.get("id")
    if not message_id:
        return jsonify({"status": "error", "message": "ID가 필요합니다."}), 400
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM liked_messages WHERE id = ? AND user_id = ?', (message_id, session['user_id']))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"status": "error", "message": "삭제 권한이 없거나 메시지를 찾을 수 없습니다."}), 404
        return jsonify({"status": "success", "message": "메시지가 삭제되었습니다."})
    except Exception as e:
        print(f"Error in /api/delete_favorite: {e}")
        conn.rollback()
        return jsonify({"status": "error", "message": "삭제 중 오류 발생"})
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    app.run(debug=True, port=5001)