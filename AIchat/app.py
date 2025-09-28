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
from datetime import datetime, timedelta

load_dotenv()
app = Flask(__name__)
app.secret_key = 'your-very-secret-key-for-aichat'

try:
    chatbot_instance = Chatbot()
except Exception as e:
    print(f"❌ Chatbot 인스턴스 생성 실패: {e}")
    chatbot_instance = None

def get_db_conn():
    conn = sqlite3.connect('chatbot_likes.db')
    conn.row_factory = sqlite3.Row
    return conn

PERSONAS = {
    "ho": { "name": "호", "prompt": PERSONA_HO_PROMPT, "profile_image": "/static/images/profile_ho.png", "greetings": GREETINGS_HO },
    "ung": { "name": "웅", "prompt": PERSONA_UNG_PROMPT, "profile_image": "/static/images/profile_ung.png", "greetings": GREETINGS_UNG }
}

def get_stage_from_score(score):
    """PHQ-9 점수에 따라 사용자 단계를 1, 2, 3, 4로 반환하는 함수"""
    if score <= 4: return 1
    if score <= 9: return 2
    if score <= 19: return 3
    return 4

@app.route("/")
def index():
    session['user_id'] = 1
    session['username'] = '홍길동'
    return render_template("index.html")

@app.route("/chat/<bot_type>")
def chat(bot_type):
    if 'user_id' not in session:
        return "로그인이 필요합니다.", 401
    persona = PERSONAS.get(bot_type)
    if not persona:
        return "챗봇을 찾을 수 없습니다.", 404
    user_id = session['user_id']
    conn = get_db_conn()
    try:
        active_session = conn.execute(
            'SELECT * FROM chat_sessions WHERE user_id = ? AND bot_type = ? AND is_active = 1',
            (user_id, bot_type)
        ).fetchone()
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
            messages = conn.execute(
                'SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC',
                (active_session['id'],)
            ).fetchall()
            initial_history = [dict(m) for m in messages]
        else:
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
    if 'user_id' not in session:
        return jsonify({"error": "로그인이 필요합니다."}), 401

    try:
        data = request.get_json()
        if data is None:
            raise ValueError("No JSON data received or Content-Type is not application/json")
    except Exception as e:
        raw_data = request.get_data(as_text=True)
        print(f"❌ JSON 디코딩 실패: {e}")
        print(f"➡️ 원본 데이터(RAW DATA) 수신 내용: {raw_data}")
        return jsonify({"error": "잘못된 요청 형식입니다. 서버 로그를 확인해주세요."}), 400

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
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, 'user', user_message)
        )
        last_message_id = cursor.lastrowid
        conn.commit()

        history_rows = conn.execute(
            'SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC', (session_id,)
        ).fetchall()
        history = [dict(row) for row in history_rows]

        bot_response = None

        is_cooldown_active = False
        eligible_date_str = ""
        latest_phq_session = conn.execute(
            'SELECT next_phq_eligible_timestamp FROM chat_sessions WHERE user_id = ? AND next_phq_eligible_timestamp IS NOT NULL ORDER BY last_phq_timestamp DESC LIMIT 1',
            (user_id,)
        ).fetchone()

        if latest_phq_session and latest_phq_session['next_phq_eligible_timestamp']:
            now_timestamp = datetime.now().timestamp()
            eligible_timestamp = latest_phq_session['next_phq_eligible_timestamp']
            if now_timestamp < eligible_timestamp:
                is_cooldown_active = True
                eligible_date_str = datetime.fromtimestamp(eligible_timestamp).strftime('%Y년 %m월 %d일')

        trigger_keywords = ["검사", "진단", "테스트", "설문", "phq"]
        if is_cooldown_active and any(keyword in user_message.lower() for keyword in trigger_keywords):
            if bot_type == 'ho':
                bot_response = f"앗, 또 마음 상태를 확인하고 싶구나! 좋아 좋아! 하지만 더 정확한 변화를 보려면 **{eligible_date_str}**까지 기다려주는 게 최고야! 그동안은 나랑 더 신나는 이야기하자! 😄"
            else: # ung
                bot_response = f"마음 상태를 꾸준히 점검하려는 마음, 정말 멋져요. 다만, 의미 있는 변화를 관찰하기 위해 다음 검사는 **{eligible_date_str}**에 진행하는 것이 좋겠습니다. 그때까지는 제가 곁에서 당신의 이야기를 들을게요. 😌"

            conn.execute("DELETE FROM messages WHERE id = ?", (last_message_id,))
            conn.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", (session_id, 'assistant', bot_response))
            conn.commit()
            return jsonify({"response": bot_response})

        phq_completed = bool(active_session['phq_completed'])

        if not phq_completed:
            is_numeric_answer = user_message in ["1", "2", "3", "4"]
            phq_answers_in_db = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user' AND content IN ('1', '2', '3', '4')",
                (session_id,)
            ).fetchone()[0]

            is_first_user_message = sum(1 for msg in history if msg['role'] == 'user') == 1

            if is_first_user_message and not is_cooldown_active:
                question_text = PHQ9_QUESTIONS[0]['question']
                options_text = "\n\n(답변: 1. 전혀 없음 / 2. 며칠 동안 / 3. 일주일 이상 / 4. 거의 매일)"
                if bot_type == 'ho':
                    intro_text = "안녕! 나는 너의 활기찬 친구 호야! 🐯\n\n본격적으로 이야기하기 전에, 간단한 마음 건강 체크부터 시작해보자! 어렵지 않으니 금방 끝날 거야."
                else: # ung
                    intro_text = "안녕하세요. 당신의 곁에서 든든한 힘이 되어줄 웅입니다. 🐻\n\n대화를 시작하기에 앞서, 잠시 당신의 마음 상태를 점검하는 시간을 갖겠습니다. 차분히 답변해주세요."
                bot_response = f"{intro_text}\n\n{question_text}{options_text}"

            elif not is_numeric_answer and phq_answers_in_db > 0:
                bot_response = "앗, 1, 2, 3, 4 중 하나의 숫자로만 골라줄 수 있을까?"
                conn.execute("DELETE FROM messages WHERE id = ?", (last_message_id,))
                conn.commit()
            elif is_numeric_answer:
                current_q_index = phq_answers_in_db
                if current_q_index < len(PHQ9_QUESTIONS):
                    next_question_data = PHQ9_QUESTIONS[current_q_index]
                    bot_response = f"{next_question_data['question']}\n\n(답변: 1. 전혀 없음 / 2. 며칠 동안 / 3. 일주일 이상 / 4. 거의 매일)"
                else:
                    answer_rows = conn.execute(
                        "SELECT content FROM messages WHERE session_id = ? AND role = 'user' AND content IN ('1', '2', '3', '4')",
                        (session_id,)
                    ).fetchall()
                    answers = [row['content'] for row in answer_rows]
                    score = sum(PHQ9_QUESTIONS[i]['options'][ans] for i, ans in enumerate(answers))
                    user_stage = get_stage_from_score(score)

                    now_dt = datetime.now()
                    last_timestamp = now_dt.timestamp()
                    if score >= 10:
                        delta = timedelta(weeks=2)
                    else:
                        delta = timedelta(weeks=4)
                    next_eligible_dt = now_dt + delta
                    next_eligible_timestamp = next_eligible_dt.timestamp()

                    conn.execute(
                        '''UPDATE chat_sessions
                           SET user_stage = ?, phq_completed = ?, last_phq_timestamp = ?, next_phq_eligible_timestamp = ?
                           WHERE id = ?''',
                        (user_stage, 1, last_timestamp, next_eligible_timestamp, session_id)
                    )

                    if bot_type == 'ho':
                        bot_response = "좋았어, 마음 점검 완료! 솔직하게 답해줘서 정말 고마워. 이제 편하게 뭐든지 이야기해 봐!"
                    else: # ung
                        bot_response = "마음 상태를 알려주셔서 감사합니다. 이제 편안하게 당신의 이야기를 들려주세요."

        if bot_response is None:
            user_stage = active_session['user_stage']
            bot_response, detected_emotion = chatbot_instance.get_response_and_emotion(
                user_input=user_message,
                persona_prompt=PERSONAS[bot_type]["prompt"],
                history=history,
                stage=user_stage if user_stage else 1
            )
            if detected_emotion != "분석실패":
                conn.execute('UPDATE messages SET emotion = ? WHERE id = ?', (detected_emotion, last_message_id))

        conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, 'assistant', bot_response)
        )

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
    user_id = session['user_id']
    session_id = request.json.get('session_id')
    conn = get_db_conn()
    try:
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