# C:/.../AIchat/app.py

import random
import sqlite3
import json
from collections import Counter
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from chatbot import Chatbot
from prompts import (
    PERSONA_HO_PROMPT, PERSONA_UNG_PROMPT, GREETINGS_HO, GREETINGS_UNG,
    PHQ9_COOLDOWN_HO, PHQ9_COOLDOWN_UNG, PHQ9_COMPLETE_HO, PHQ9_COMPLETE_UNG,
    PHQ9_QUESTIONS, SCENARIOS
)
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = 'your-very-secret-key-for-aichat'

try:
    chatbot_instance = Chatbot()
except Exception as e:
    print(f"❌ Chatbot 인스턴스 생성 실패: {e}")
    chatbot_instance = None

PERSONAS = {
    "ho": { "name": "호", "prompt": PERSONA_HO_PROMPT, "profile_image": "/static/images/profile_ho.png", "greetings": GREETINGS_HO },
    "ung": { "name": "웅", "prompt": PERSONA_UNG_PROMPT, "profile_image": "/static/images/profile_ung.png", "greetings": GREETINGS_UNG }
}

def get_db_conn():
    conn = sqlite3.connect('chatbot_likes.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_stage_from_score(score):
    if score <= 4: return "1"
    if score <= 9: return "2"
    if score <= 19: return "3"
    return "4"

# --- 페이지 렌더링 라우트 ---

@app.route("/")
def index():
    session['user_id'] = 1
    session['username'] = '홍길동'
    return render_template("index.html")

@app.route("/chat/<bot_type>")
def chat(bot_type):
    if 'user_id' not in session: return "로그인이 필요합니다.", 401
    persona = PERSONAS.get(bot_type)
    if not persona: return "챗봇을 찾을 수 없습니다.", 404
    user_id = session['user_id']
    conn = get_db_conn()
    session_id = None
    try:
        active_session = conn.execute('SELECT * FROM chat_sessions WHERE user_id = ? AND bot_type = ? AND is_active = 1', (user_id, bot_type)).fetchone()
        if not active_session:
            latest_session = conn.execute('SELECT * FROM chat_sessions WHERE user_id = ? AND bot_type = ? ORDER BY created_at DESC LIMIT 1', (user_id, bot_type)).fetchone()
            if latest_session:
                conn.execute('UPDATE chat_sessions SET is_active = 1 WHERE id = ?', (latest_session['id'],))
                conn.commit()
                active_session = conn.execute('SELECT * FROM chat_sessions WHERE id = ?', (latest_session['id'],)).fetchone()

        initial_history = []
        if active_session:
            session_id = active_session['id']
            messages = conn.execute('SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC', (session_id,)).fetchall()
            initial_history = [dict(m) for m in messages]
        else:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO chat_sessions (user_id, bot_type, session_name) VALUES (?, ?, ?)", (user_id, bot_type, "새로운 대화"))
            session_id = cursor.lastrowid
            welcome_message = random.choice(persona["greetings"])
            initial_history = [{"role": "assistant", "content": welcome_message}]
            conn.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", (session_id, "assistant", welcome_message))
            conn.commit()
    finally:
        conn.close()

    return render_template(
        "chat.html",
        bot_name=persona["name"],
        bot_type=bot_type,
        profile_image=persona["profile_image"],
        session_id=session_id,
        initial_history=json.dumps(initial_history, ensure_ascii=False)
    )

@app.route('/analysis/<int:session_id>')
def analysis(session_id):
    if 'user_id' not in session: return "로그인이 필요합니다.", 401
    conn = get_db_conn()
    try:
        session_info = conn.execute('SELECT bot_type FROM chat_sessions WHERE id = ? AND user_id = ?', (session_id, session['user_id'])).fetchone()
        if not session_info: return "세션 정보를 찾을 수 없거나 권한이 없습니다.", 404
        bot_type = session_info['bot_type']
        user_messages = conn.execute("SELECT emotion FROM messages WHERE session_id = ? AND role = 'user' AND emotion IS NOT NULL", (session_id,)).fetchall()
        user_emotions = [msg['emotion'] for msg in user_messages]
        most_common_emotion_text = "아직 분석할 대화가 충분하지 않습니다."
        if user_emotions:
            emotion_counts = Counter(user_emotions)
            if emotion_counts:
                most_common = emotion_counts.most_common(1)[0][0]
                most_common_emotion_text = f'이 대화에서 당신의 주된 감정은 **"{most_common}"** 입니다.'
        emotion_distribution = Counter(user_emotions)
        chart_data = { "labels": list(emotion_distribution.keys()), "datasets": [{ "data": list(emotion_distribution.values()), "backgroundColor": ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#C9CBCF'] }] }
    finally:
        conn.close()
    return render_template('analysis.html', session_id=session_id, bot_type=bot_type, chart_data=json.dumps(chart_data, ensure_ascii=False), most_common_emotion_text=most_common_emotion_text)

@app.route("/favorites")
def favorites():
    if 'user_id' not in session: return "로그인이 필요합니다.", 401
    return render_template("favorites.html")

# --- API 라우트 ---

# ⭐ [핵심 추가] 사이드바가 현재 대화 정보를 요청할 때 사용하는 API
@app.route("/api/get_session_info")
def get_session_info():
    session_id = request.args.get('session_id')
    if not session_id: return jsonify({"error": "Session ID is required"}), 400
    conn = get_db_conn()
    try:
        session_info = conn.execute('SELECT id, session_name, created_at FROM chat_sessions WHERE id = ?', (session_id,)).fetchone()
        if session_info:
            return jsonify(dict(session_info))
        else:
            return jsonify({"error": "Session not found"}), 404
    finally:
        if conn: conn.close()

@app.route("/api/chat", methods=["POST"])
def api_chat():
    if 'user_id' not in session: return jsonify({"error": "로그인이 필요합니다."}), 401
    data = request.json
    user_message, bot_type = data.get("message", "").strip(), data.get("bot_type")
    user_id = session['user_id']

    conn = get_db_conn()
    try:
        active_session = conn.execute('SELECT * FROM chat_sessions WHERE user_id = ? AND bot_type = ? AND is_active = 1', (user_id, bot_type)).fetchone()
        session_id = active_session['id']
        conn.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", (session_id, 'user', user_message))
        last_user_message_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()

        bot_response = None
        user_requests_test = any(keyword in user_message.lower() for keyword in ["검사", "진단", "테스트", "설문", "phq"])
        latest_phq_session = conn.execute('SELECT next_phq_eligible_timestamp FROM chat_sessions WHERE user_id = ? AND phq_completed = 1 ORDER BY last_phq_timestamp DESC LIMIT 1', (user_id,)).fetchone()

        if latest_phq_session and datetime.now().timestamp() < latest_phq_session['next_phq_eligible_timestamp'] and user_requests_test:
            eligible_date_str = datetime.fromtimestamp(latest_phq_session['next_phq_eligible_timestamp']).strftime('%Y년 %m월 %d일')
            bot_response = PHQ9_COOLDOWN_HO.format(eligible_date=eligible_date_str) if bot_type == 'ho' else PHQ9_COOLDOWN_UNG.format(eligible_date=eligible_date_str)
            conn.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", (session_id, 'assistant', bot_response))
            conn.commit()
            return jsonify({"response": bot_response})

        phq_progress = active_session['phq_progress']
        if phq_progress > -1:
            score = chatbot_instance.analyze_phq_answer(user_message, phq_progress)
            if score == -1:
                bot_response = "미안, 방금 한 말을 잘 이해하지 못했어. 조금만 더 자세히 말해줄 수 있을까?" if bot_type == 'ho' else "죄송합니다, 방금 하신 말씀을 제가 정확히 이해하지 못했습니다. 조금 더 자세히 설명해주시겠어요?"
            else:
                scores_str = active_session['phq_scores'] or ""
                scores = scores_str.split(',') if scores_str and scores_str.strip() else []
                scores.append(str(score))
                new_progress = phq_progress + 1
                conn.execute('UPDATE chat_sessions SET phq_scores = ?, phq_progress = ? WHERE id = ?', (','.join(scores), new_progress, session_id))
                conn.commit()
                if new_progress < len(PHQ9_QUESTIONS):
                    bot_response = PHQ9_QUESTIONS[new_progress][f'question_{bot_type}']
                else:
                    total_score = sum(int(s) for s in scores)
                    user_stage = get_stage_from_score(total_score)
                    now_dt, delta = datetime.now(), timedelta(weeks=2 if user_stage in ["3", "4"] else 4)
                    conn.execute('UPDATE chat_sessions SET phq_completed = 1, user_stage = ?, last_phq_timestamp = ?, next_phq_eligible_timestamp = ?, phq_progress = -1, phq_scores = ? WHERE id = ?',
                                 (user_stage, now_dt.timestamp(), (now_dt + delta).timestamp(), ','.join(scores), session_id))
                    bot_response = PHQ9_COMPLETE_HO if bot_type == 'ho' else PHQ9_COMPLETE_UNG
        else:
            history = [dict(row) for row in conn.execute('SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC', (session_id,)).fetchall()]
            is_first_user_message = sum(1 for msg in history if msg['role'] == 'user') == 1
            if (is_first_user_message and not bool(latest_phq_session)) or user_requests_test:
                conn.execute('UPDATE chat_sessions SET phq_progress = 0 WHERE id = ?', (session_id,))
                conn.commit()
                intro = "안녕! 나는 너의 활기찬 친구 호야! 🐯\n\n본격적으로 이야기하기 전에, 요즘 어떻게 지내는지 좀 알려주라!" if bot_type == 'ho' else "안녕하세요. 당신의 곁에서 든든한 힘이 되어줄 웅입니다. 🐻\n\n대화를 시작하기에 앞서, 당신의 마음에 대해 조금 더 알아보기 위해 몇 가지 질문을 드려도 괜찮을까요?"
                bot_response = f"{intro}\n\n{PHQ9_QUESTIONS[0][f'question_{bot_type}']}"

        if bot_response is None:
            history = [dict(row) for row in conn.execute('SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC', (session_id,)).fetchall()]
            user_stage = active_session['user_stage'] or "1"
            bot_response, detected_emotion = chatbot_instance.get_response_and_emotion(user_input=user_message, persona_prompt=PERSONAS[bot_type]["prompt"], history=history, stage=user_stage)
            if detected_emotion and detected_emotion != "분석실패":
                conn.execute('UPDATE messages SET emotion = ? WHERE id = ?', (detected_emotion, last_user_message_id))

        conn.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", (session_id, 'assistant', bot_response))
        if active_session['session_name'] == "새로운 대화":
            conn.execute('UPDATE chat_sessions SET session_name = ? WHERE id = ?', (user_message[:50], session_id))
        conn.commit()
        return jsonify({"response": bot_response})
    except Exception as e:
        print(f"Error in /api/chat: {e}")
        if conn: conn.rollback()
        return jsonify({"error": "서버 처리 중 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()

# ... (new_chat 이하 모든 다른 라우트들은 이전과 동일하게 유지됩니다.) ...
@app.route("/api/new_chat", methods=["POST"])
def new_chat():
    user_id = session['user_id']
    bot_type = request.json.get('bot_type')
    conn = get_db_conn()
    try:
        conn.execute('UPDATE chat_sessions SET is_active = 0 WHERE user_id = ? AND bot_type = ?', (user_id, bot_type))
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_sessions (user_id, bot_type, session_name, is_active) VALUES (?, ?, ?, 1)", (user_id, bot_type, "새로운 대화"))
        new_session_id = cursor.lastrowid
        welcome_message = random.choice(PERSONAS[bot_type]["greetings"])
        new_history = [{"role": "assistant", "content": welcome_message}]
        conn.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", (new_session_id, "assistant", welcome_message))
        conn.commit()
        return jsonify({"history": new_history, "session_id": new_session_id})
    except Exception as e:
        print(f"Error in /api/new_chat: {e}")
        conn.rollback()
        return jsonify({"error": "새 대화 생성 중 오류 발생"}), 500
    finally:
        if conn: conn.close()

@app.route("/api/past_chats", methods=["GET"])
def get_past_chats():
    user_id = session['user_id']
    bot_type = request.args.get('bot_type')
    conn = get_db_conn()
    try:
        past_chats = conn.execute('SELECT id, session_name, created_at FROM chat_sessions WHERE user_id = ? AND bot_type = ? AND is_active = 0 ORDER BY created_at DESC', (user_id, bot_type)).fetchall()
        return jsonify([dict(row) for row in past_chats])
    finally:
        if conn: conn.close()

@app.route("/api/load_chat", methods=["POST"])
def load_chat():
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
        if conn: conn.close()

@app.route("/api/delete_session", methods=["POST"])
def delete_session():
    user_id = session['user_id']
    session_id = request.json.get('session_id')
    conn = get_db_conn()
    try:
        cursor = conn.execute('DELETE FROM chat_sessions WHERE id = ? AND user_id = ?', (session_id, user_id))
        conn.commit()
        if cursor.rowcount == 0: return jsonify({"status": "error", "message": "삭제 권한이 없거나 세션을 찾을 수 없습니다."}), 404
        return jsonify({"status": "success", "message": "대화가 삭제되었습니다."})
    except Exception as e:
        print(f"Error in /api/delete_session: {e}")
        conn.rollback()
        return jsonify({"error": "대화 삭제 중 오류 발생"}), 500
    finally:
        if conn: conn.close()

@app.route("/api/like_message", methods=["POST"])
def like_message():
    if 'user_id' not in session: return jsonify({"status": "error", "message": "로그인이 필요합니다."}), 401
    data = request.json
    conn = get_db_conn()
    try:
        conn.execute('INSERT INTO liked_messages (user_id, bot_type, message) VALUES (?, ?, ?)', (session['user_id'], data.get("bot_type"), data.get("message")))
        conn.commit()
        return jsonify({"status": "success", "message": "메시지를 저장했습니다."})
    except Exception as e:
        print(f"Error in /api/like_message: {e}")
        conn.rollback()
        return jsonify({"status": "error", "message": "메시지 저장 중 오류 발생"})
    finally:
        if conn: conn.close()

@app.route("/api/favorites", methods=["GET"])
def get_favorites():
    if 'user_id' not in session: return jsonify({"error": "로그인이 필요합니다."}), 401
    conn = get_db_conn()
    try:
        messages = conn.execute('SELECT id, bot_type, message, liked_at, CASE bot_type WHEN "ho" THEN "호" WHEN "ung" THEN "웅" ELSE "알 수 없음" END as bot_name FROM liked_messages WHERE user_id = ? ORDER BY liked_at DESC', (session['user_id'],)).fetchall()
        return jsonify([dict(row) for row in messages])
    except Exception as e:
        print(f"Error in /api/favorites: {e}")
        return jsonify({"error": "데이터를 불러오는 중 오류가 발생했습니다."}), 500
    finally:
        if conn: conn.close()

@app.route("/api/delete_favorite", methods=["POST"])
def delete_favorite():
    if 'user_id' not in session: return jsonify({"status": "error", "message": "로그인이 필요합니다."}), 401
    message_id = request.json.get("id")
    if not message_id: return jsonify({"status": "error", "message": "ID가 필요합니다."}), 400
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM liked_messages WHERE id = ? AND user_id = ?', (message_id, session['user_id']))
        conn.commit()
        if cursor.rowcount == 0: return jsonify({"status": "error", "message": "삭제 권한이 없거나 메시지를 찾을 수 없습니다."}), 404
        return jsonify({"status": "success", "message": "메시지가 삭제되었습니다."})
    except Exception as e:
        print(f"Error in /api/delete_favorite: {e}")
        conn.rollback()
        return jsonify({"status": "error", "message": "삭제 중 오류 발생"})
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    app.run(debug=True, port=5001)