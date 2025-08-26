# C:/Users/zxzx0/Downloads/AIChatBot/AIchat/app.py

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

chatbot_instance = Chatbot()

def get_db_conn():
    conn = sqlite3.connect('chatbot_likes.db')
    conn.row_factory = sqlite3.Row
    return conn

PERSONAS = {
    "ho": { "name": "호", "prompt": PERSONA_HO_PROMPT, "profile_image": "/static/images/profile_ho.png", "greetings": GREETINGS_HO },
    "ung": { "name": "웅", "prompt": PERSONA_UNG_PROMPT, "profile_image": "/static/images/profile_ung.png", "greetings": GREETINGS_UNG }
}

def get_stage_from_score(score):
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

    active_session = conn.execute(
        'SELECT * FROM chat_sessions WHERE user_id = ? AND bot_type = ? AND is_active = 1',
        (user_id, bot_type)
    ).fetchone()

    if active_session:
        initial_history = json.loads(active_session['history_json'])
        # ✨ [복구] 현재 세션의 감정 요약 데이터도 불러옵니다.
        initial_emotion_summary = json.loads(active_session['emotion_summary_json'])
    else:
        welcome_message = random.choice(persona["greetings"])
        initial_history = [{"role": "assistant", "content": welcome_message}]
        # ✨ [복구] 새 대화 시작 시 감정 요약 데이터는 빈 딕셔너리로 초기화합니다.
        initial_emotion_summary = {}
        cursor = conn.cursor()
        # ✨ [복구] 새 세션을 만들 때 emotion_summary_json 필드도 함께 추가합니다.
        cursor.execute(
            """INSERT INTO chat_sessions (user_id, bot_type, history_json, session_name, emotion_summary_json)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, bot_type, json.dumps(initial_history, ensure_ascii=False), "새로운 대화", json.dumps(initial_emotion_summary))
        )
        conn.commit()

    conn.close()

    return render_template(
        "chat.html",
        bot_name=persona["name"],
        profile_image=persona["profile_image"],
        bot_type=bot_type,
        initial_history=json.dumps(initial_history, ensure_ascii=False),
        # ✨ [복구] 감정 요약 데이터를 템플릿으로 전달합니다.
        initial_emotion_summary=json.dumps(initial_emotion_summary)
    )

@app.route("/api/chat", methods=["POST"])
def api_chat():
    if 'user_id' not in session:
        return jsonify({"error": "로그인이 필요합니다."}), 401

    data = request.json
    user_message = data.get("message", "").strip()
    bot_type = data.get("bot_type")
    user_id = session['user_id']

    if not user_message or not bot_type:
        return jsonify({"error": "필수 정보가 누락되었습니다."}), 400

    conn = get_db_conn()
    try:
        active_session = conn.execute(
            'SELECT * FROM chat_sessions WHERE user_id = ? AND bot_type = ? AND is_active = 1',
            (user_id, bot_type)
        ).fetchone()

        if not active_session:
            return jsonify({"error": "활성 채팅 세션을 찾을 수 없습니다."}), 404

        history = json.loads(active_session['history_json'])
        phq_completed = bool(active_session['phq_completed'])
        user_stage = active_session['user_stage']
        # ✨ [복구] DB에서 현재 감정 요약 데이터를 불러옵니다.
        emotion_summary = json.loads(active_session['emotion_summary_json'])

        history.append({"role": "user", "content": user_message})

        if active_session['session_name'] == "새로운 대화":
            session_name = user_message[:50]
            conn.execute('UPDATE chat_sessions SET session_name = ? WHERE id = ?', (session_name, active_session['id']))

        bot_response = None
        detected_emotion = "중립"
        is_first_user_message = sum(1 for msg in history if msg['role'] == 'user') == 1

        # --- PHQ-9 설문 로직 (변경 없음) ---
        if not phq_completed and is_first_user_message:
            question_text = PHQ9_QUESTIONS[0]['question']
            options_text = "\n\n(답변: 1. 전혀 없음 / 2. 며칠 동안 / 3. 일주일 이상 / 4. 거의 매일)"
            bot_response = f"이야기를 시작하기 전에, 잠시 당신의 마음 상태를 점검해볼게요.\n\n{question_text}{options_text}"
        elif not phq_completed and len(history) > 2 and "며칠 동안" in history[-2]['content']:
            if user_message not in ["1", "2", "3", "4"]:
                bot_response = "앗, 1, 2, 3, 4 중 하나의 숫자로만 골라줄 수 있을까?"
                history.pop()
            else:
                phq_user_answers = [msg['content'] for msg in history if msg['role'] == 'user' and msg['content'] in ["1", "2", "3", "4"]]
                current_q_index = len(phq_user_answers) - 1
                if current_q_index + 1 < len(PHQ9_QUESTIONS):
                    next_question_data = PHQ9_QUESTIONS[current_q_index + 1]
                    bot_response = f"{next_question_data['question']}\n\n(답변: 1. 전혀 없음 / 2. 며칠 동안 / 3. 일주일 이상 / 4. 거의 매일)"
                else:
                    score = sum(PHQ9_QUESTIONS[i]['options'][ans] for i, ans in enumerate(phq_user_answers))
                    user_stage = get_stage_from_score(score)
                    phq_completed = True
                    conn.execute('UPDATE chat_sessions SET user_stage = ?, phq_completed = ? WHERE id = ?', (user_stage, 1, active_session['id']))
                    bot_response = "마음 점검이 완료되었습니다. 이야기 나눠주셔서 감사해요. 이제 편하게 당신의 이야기를 들려주세요."

        # --- 일반 대화 및 감정 분석 로직 ---
        if bot_response is None:
            # ✨ [복구] get_response는 (응답, 감정) 튜플을 반환합니다.
            bot_response, detected_emotion = chatbot_instance.get_response_and_emotion(
                user_input=user_message,
                persona_prompt=PERSONAS[bot_type]["prompt"],
                history=history,
                stage=user_stage
            )


            if detected_emotion != "분석실패":
                # 1. 현재 대화의 감정 요약 업데이트
                emotion_summary[detected_emotion] = emotion_summary.get(detected_emotion, 0) + 1
                # 2. 전체 감정 로그 테이블에 기록 (init_db.py에 emotion_logs 테이블이 있어야 함)
                # conn.execute(
                #     'INSERT INTO emotion_logs (session_id, user_id, bot_type, emotion) VALUES (?, ?, ?, ?)',
                #     (active_session['id'], user_id, bot_type, detected_emotion)
                # )

        history.append({"role": "assistant", "content": bot_response})

        # ✨ [복구] DB 업데이트 시, history와 함께 감정 요약 데이터도 저장합니다.
        conn.execute(
            'UPDATE chat_sessions SET history_json = ?, emotion_summary_json = ? WHERE id = ?',
            (json.dumps(history, ensure_ascii=False), json.dumps(emotion_summary), active_session['id'])
        )
        conn.commit()

        # ✨ [복구] API 응답에 감정 요약 데이터를 포함시켜 프론트엔드로 전달합니다.
        return jsonify({"response": bot_response, "emotion_summary": emotion_summary})

    except Exception as e:
        print(f"Error in /api/chat: {e}")
        return jsonify({"error": "서버 처리 중 오류가 발생했습니다."}), 500
    finally:
        if conn:
            conn.close()

# (이하 다른 라우트들은 생략)
# ...
@app.route("/api/new_chat", methods=["POST"])
def new_chat():
    user_id = session['user_id']
    bot_type = request.json.get('bot_type')
    conn = get_db_conn()
    try:
        conn.execute('UPDATE chat_sessions SET is_active = 0 WHERE user_id = ? AND bot_type = ? AND is_active = 1', (user_id, bot_type))

        welcome_message = random.choice(PERSONAS[bot_type]["greetings"])
        new_history = [{"role": "assistant", "content": welcome_message}]
        new_emotion_summary = {} # 새 대화 시작 시 감정 요약 초기화
        conn.execute(
            """INSERT INTO chat_sessions (user_id, bot_type, history_json, session_name, is_active, emotion_summary_json)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (user_id, bot_type, json.dumps(new_history, ensure_ascii=False), "새로운 대화", json.dumps(new_emotion_summary))
        )
        conn.commit()
        return jsonify({"history": new_history, "emotion_summary": new_emotion_summary})
    except Exception as e:
        print(f"Error in /api/new_chat: {e}")
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
        conn.execute('UPDATE chat_sessions SET is_active = 0 WHERE user_id = ? AND bot_type = ? AND is_active = 1', (user_id, bot_type))
        conn.execute('UPDATE chat_sessions SET is_active = 1 WHERE id = ? AND user_id = ?', (session_id_to_load, user_id))

        loaded_session = conn.execute('SELECT history_json, emotion_summary_json FROM chat_sessions WHERE id = ?', (session_id_to_load,)).fetchone()
        conn.commit()

        history = json.loads(loaded_session['history_json'])
        emotion_summary = json.loads(loaded_session['emotion_summary_json'])
        return jsonify({"history": history, "emotion_summary": emotion_summary})
    except Exception as e:
        print(f"Error in /api/load_chat: {e}")
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
        return jsonify({"error": "대화 삭제 중 오류 발생"}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/like_message", methods=["POST"])
def like_message():
    if 'user_id' not in session: return jsonify({"status": "error", "message": "로그인이 필요합니다."}), 401
    data = request.json
    conn = get_db_conn()
    conn.execute('INSERT INTO liked_messages (user_id, bot_type, message) VALUES (?, ?, ?)',
                 (session['user_id'], data.get("bot_type"), data.get("message")))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "메시지를 저장했습니다."})

# ✨ [이동] /analysis 라우트를 if __name__ 바깥으로 옮겼습니다.
@app.route("/analysis/<bot_type>")
def analysis(bot_type):
    """감정 분석 그래프를 보여주는 별도의 페이지를 렌더링합니다."""
    if 'user_id' not in session:
        return "로그인이 필요합니다.", 401

    persona = PERSONAS.get(bot_type)
    if not persona:
        return "챗봇을 찾을 수 없습니다.", 404

    user_id = session['user_id']
    conn = get_db_conn()
    try:
        # 현재 진행중인(active) 세션의 감정 데이터만 가져옵니다.
        active_session = conn.execute(
            'SELECT emotion_summary_json FROM chat_sessions WHERE user_id = ? AND bot_type = ? AND is_active = 1',
            (user_id, bot_type)
        ).fetchone()

        if active_session and active_session['emotion_summary_json']:
            emotion_data = json.loads(active_session['emotion_summary_json'])
        else:
            # 활성 세션이 없거나 감정 데이터가 없는 경우
            emotion_data = {}

    finally:
        if conn:
            conn.close()

    return render_template(
        "analysis.html",
        bot_name=persona["name"],
        bot_type=bot_type,
        emotion_data=emotion_data # 데이터를 JSON 문자열로 전달
    )

# '저장한 문구' 페이지와 관련된 라우트들

@app.route("/favorites")
def favorites():
    """'저장한 문구' 페이지를 렌더링합니다."""
    if 'user_id' not in session:
        return "로그인이 필요합니다.", 401
    return render_template("favorites.html")

@app.route("/api/favorites", methods=["GET"])
def get_favorites():
    """저장된 모든 문구를 DB에서 가져와 JSON으로 반환합니다."""
    if 'user_id' not in session:
        return jsonify({"error": "로그인이 필요합니다."}), 401

    conn = get_db_conn()
    try:
        # bot_type에 따라 챗봇 이름을 함께 조회하고, liked_at도 가져옵니다.
        messages = conn.execute('''
                                SELECT
                                    id, bot_type, message, liked_at,
                                    CASE bot_type
                                        WHEN 'ho' THEN '호'
                                        WHEN 'ung' THEN '웅'
                                        ELSE '알 수 없음'
                                        END as bot_name
                                FROM liked_messages
                                WHERE user_id = ?
                                ORDER BY liked_at DESC
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
    """저장된 문구를 DB에서 삭제합니다."""
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "로그인이 필요합니다."}), 401

    data = request.json
    message_id = data.get("id")
    if not message_id:
        return jsonify({"status": "error", "message": "ID가 필요합니다."}), 400

    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        # 본인의 메시지만 삭제할 수 있도록 user_id 조건 추가
        cursor.execute('DELETE FROM liked_messages WHERE id = ? AND user_id = ?', (message_id, session['user_id']))
        conn.commit()

        if cursor.rowcount == 0:
            # 삭제된 행이 없으면 권한이 없거나 메시지가 없는 경우
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