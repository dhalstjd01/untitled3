import random
import sqlite3
import json
from collections import Counter
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from chatbot import Chatbot
from prompts import (
    PERSONA_HO_PROMPT, PERSONA_UNG_PROMPT,
    GREETINGS_HO, GREETINGS_UNG,
    PHQ9_QUESTIONS, SCENARIOS
)

# --- 1. 전역 설정 및 초기화 ---
load_dotenv()
app = Flask(__name__)
app.secret_key = 'your-very-secret-key-for-aichat'

# 챗봇 인스턴스는 앱 실행 시 한 번만 생성하여 재사용합니다.
try:
    chatbot_instance = Chatbot()
except Exception as e:
    print(f"❌ Chatbot 인스턴스 생성 실패: {e}")
    chatbot_instance = None

PERSONAS = {
    "ho": { "name": "호", "prompt": PERSONA_HO_PROMPT, "profile_image": "/static/images/profile_ho.png", "greetings": GREETINGS_HO },
    "ung": { "name": "웅", "prompt": PERSONA_UNG_PROMPT, "profile_image": "/static/images/profile_ung.png", "greetings": GREETINGS_UNG }
}

# --- 2. 헬퍼 함수 ---
def get_db_conn():
    """데이터베이스 연결 객체를 반환하는 함수"""
    conn = sqlite3.connect('chatbot_likes.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_stage_from_score(score):
    """PHQ-9 점수에 따라 사용자 단계를 반환하는 함수"""
    if score <= 4: return 1
    if score <= 9: return 2
    if score <= 19: return 3
    return 4

# --- 3. 페이지 렌더링 라우트 ---
@app.route("/")
def index():
    """메인 페이지. 데모를 위해 user_id=1로 자동 로그인합니다."""
    session['user_id'] = 1
    session['username'] = '홍길동'
    return render_template("index.html")

@app.route("/chat/<bot_type>")
def chat(bot_type):
    """채팅 페이지를 렌더링하고, 기존/신규 세션을 관리합니다."""
    if 'user_id' not in session:
        return "로그인이 필요합니다.", 401

    persona = PERSONAS.get(bot_type)
    if not persona:
        return "챗봇을 찾을 수 없습니다.", 404

    user_id = session['user_id']
    conn = get_db_conn()
    session_id = None
    try:
        # 1. 현재 활성(active) 세션을 찾습니다.
        active_session = conn.execute(
            'SELECT * FROM chat_sessions WHERE user_id = ? AND bot_type = ? AND is_active = 1',
            (user_id, bot_type)
        ).fetchone()

        # 2. 활성 세션이 없다면, 가장 최근 세션을 찾아 활성화합니다.
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
            # 3. 활성 세션이 있으면, ID를 가져오고 메시지를 불러옵니다.
            session_id = active_session['id']
            messages = conn.execute(
                'SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC',
                (session_id,)
            ).fetchall()
            initial_history = [dict(m) for m in messages]
        else:
            # 4. 어떤 세션도 없다면, 새로운 세션을 생성하고 ID를 가져옵니다.
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO chat_sessions (user_id, bot_type, session_name, is_active) VALUES (?, ?, ?, 1)",
                (user_id, bot_type, "새로운 대화")
            )
            session_id = cursor.lastrowid

            welcome_message = random.choice(persona["greetings"])
            initial_history = [{"role": "assistant", "content": welcome_message}]
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, "assistant", welcome_message)
            )
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

@app.route("/favorites")
def favorites():
    """저장한 메시지 보기 페이지"""
    if 'user_id' not in session:
        return "로그인이 필요합니다.", 401
    return render_template("favorites.html")

# C:/Users/zxzx0/Desktop/chatbot/untitled3/AIchat/app.py

@app.route('/analysis/<int:session_id>')
def analysis(session_id):
    """
    [진단 기능 추가] 사용자의 감정 데이터를 집계하고,
    진단 정보를 포함하여 템플릿에 전달합니다.
    """
    if 'user_id' not in session:
        return "로그인이 필요합니다.", 401

    conn = get_db_conn()
    bot_type = 'ho'  # 기본값 설정
    chart_data = {}  # 기본값 설정
    try:
        # "채팅으로 돌아가기" 버튼을 위해 bot_type을 조회합니다.
        session_info = conn.execute('SELECT bot_type FROM chat_sessions WHERE id = ?', (session_id,)).fetchone()
        if session_info:
            bot_type = session_info['bot_type']

        # DB에서 해당 세션의 '사용자' 감정 기록만 가져옵니다.
        user_messages_with_emotion = conn.execute(
            "SELECT emotion FROM messages WHERE session_id = ? AND role = 'user' AND emotion IS NOT NULL",
            (session_id,)
        ).fetchall()

        user_emotions = [msg['emotion'] for msg in user_messages_with_emotion]

        # --- 상단 텍스트 생성 ---
        most_common_emotion_text = "아직 분석할 대화가 충분하지 않습니다."
        if user_emotions:
            recent_emotions = user_emotions[-20:]
            emotion_counts = Counter(recent_emotions)
            if emotion_counts:
                most_common_emotion = emotion_counts.most_common(1)[0][0]
                most_common_emotion_text = f'최근 20개 대화에서 당신의 주된 감정은 **"{most_common_emotion}"** 입니다.'

        # --- 원형 그래프 데이터 생성 ---
        emotion_distribution = Counter(user_emotions)

        chart_data = {
            "labels": list(emotion_distribution.keys()),
            "datasets": [{
                "label": "감정 분포",
                "data": list(emotion_distribution.values()),
                "backgroundColor": [
                    'rgba(255, 99, 132, 0.7)', 'rgba(54, 162, 235, 0.7)',
                    'rgba(255, 206, 86, 0.7)', 'rgba(75, 192, 192, 0.7)',
                    'rgba(153, 102, 255, 0.7)', 'rgba(255, 159, 64, 0.7)',
                    'rgba(199, 199, 199, 0.7)'
                ],
                "borderColor": '#ffffff',
                "borderWidth": 2
            }]
        }
    finally:
        conn.close()

    return render_template(
        'analysis.html',
        session_id=session_id,
        bot_type=bot_type,  # "채팅으로 돌아가기" 버튼을 위해 전달
        chart_data=json.dumps(chart_data, indent=2, ensure_ascii=False),  # 진단용으로 보기 좋게 포맷
        most_common_emotion_text=most_common_emotion_text
    )

# --- 4. API 라우트 ---

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    [최종 안정화] 사용자 메시지와 감정을 먼저 저장(commit)하여 데이터 누락을 방지합니다.
    """
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
            # 활성 세션이 없으면 오류 대신 새 세션을 만들어주는 것이 더 안정적일 수 있으나,
            # 현재 로직에서는 chat.html 진입 시 무조건 세션이 생성되므로 404가 맞습니다.
            return jsonify({"error": "활성 채팅 세션을 찾을 수 없습니다."}), 404

        session_id = active_session['id']

        # --- 1. 사용자 감정 분석 ---
        user_emotion = None
        if chatbot_instance and hasattr(chatbot_instance, 'emotion_analyzer'):
            user_emotion = chatbot_instance.emotion_analyzer.analyze_emotion(user_message)
            print(f"✅ 사용자 감정 분석 결과: {user_emotion}")

        # --- 2. 사용자 메시지와 감정을 먼저 저장하고 즉시 커밋 ---
        conn.execute(
            "INSERT INTO messages (session_id, role, content, emotion) VALUES (?, ?, ?, ?)",
            (session_id, 'user', user_message, user_emotion if user_emotion and user_emotion != "분석실패" else None)
        )
        conn.commit() # <--- 여기서 먼저 저장하여 데이터를 안전하게 확보!

        # --- 3. 챗봇 응답 생성 (이제부터 발생하는 오류는 위 데이터에 영향을 주지 않음) ---
        history_rows = conn.execute(
            'SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC', (session_id,)
        ).fetchall()
        history = [dict(row) for row in history_rows]

        bot_response = None
        phq_completed = bool(active_session['phq_completed'])
        user_stage = active_session['user_stage']

        # (PHQ-9 설문 로직)
        if not phq_completed:
            is_numeric_answer = user_message in ["1", "2", "3", "4"]
            # 숫자 답변 개수는 새로 추가된 메시지를 포함하여 다시 계산
            phq_answers_in_db = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user' AND content IN ('1', '2', '3', '4')",
                (session_id,)
            ).fetchone()[0]

            # 첫 사용자 메시지인지 확인 (인사말 제외)!
            user_message_count = conn.execute("SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'", (session_id,)).fetchone()[0]

            if user_message_count == 1:
                question_text = PHQ9_QUESTIONS[0]['question']
                options_text = "\n\n(답변: 1. 전혀 없음 / 2. 며칠 동안 / 3. 일주일 이상 / 4. 거의 매일)"
                bot_response = f"이야기를 시작하기 전에, 잠시 당신의 마음 상태를 점검해볼게요.\n\n{question_text}{options_text}"
            elif not is_numeric_answer and phq_answers_in_db > 0:
                # 이 부분은 숫자 답변을 유도하는 것이므로, 사용자 메시지를 삭제하지 않고 그대로 둡니다.
                bot_response = "앗, 1, 2, 3, 4 중 하나의 숫자로만 골라줄 수 있을까?"
            elif is_numeric_answer:
                if phq_answers_in_db < len(PHQ9_QUESTIONS):
                    next_question_data = PHQ9_QUESTIONS[phq_answers_in_db]
                    bot_response = f"{next_question_data['question']}\n\n(답변: 1. 전혀 없음 / 2. 며칠 동안 / 3. 일주일 이상 / 4. 거의 매일)"
                else: # 마지막 답변인 경우
                    # 점수 계산을 위해 모든 숫자 답변을 다시 가져옴
                    answer_rows = conn.execute(
                        "SELECT content FROM messages WHERE session_id = ? AND role = 'user' AND content IN ('1', '2', '3', '4') ORDER BY created_at ASC",
                        (session_id,)
                    ).fetchall()
                    answers = [row['content'] for row in answer_rows]
                    score = sum(PHQ9_QUESTIONS[i]['options'][ans] for i, ans in enumerate(answers))
                    user_stage = get_stage_from_score(score)
                    conn.execute('UPDATE chat_sessions SET user_stage = ?, phq_completed = ? WHERE id = ?', (user_stage, 1, session_id))
                    bot_response = "마음 점검이 완료되었습니다. 이야기 나눠주셔서 감사해요. 이제 편하게 당신의 이야기를 들려주세요."

        # 일반 대화 응답 생성
        if bot_response is None:
            bot_response, _ = chatbot_instance.get_response_and_emotion(
                user_input=user_message,
                persona_prompt=PERSONAS[bot_type]["prompt"],
                history=history,
                stage=user_stage,
                pre_analyzed_emotion=user_emotion
            )

        # 4. 봇 응답을 DB에 저장
        conn.execute(
            "INSERT INTO messages (session_id, role, content, emotion) VALUES (?, ?, ?, ?)",
            (session_id, 'assistant', bot_response, None)
        )

        # 5. 세션 이름 업데이트
        if active_session['session_name'] == "새로운 대화":
            conn.execute('UPDATE chat_sessions SET session_name = ? WHERE id = ?', (user_message[:50], session_id))

        conn.commit() # 봇 응답 및 세션 이름 변경사항 최종 저장
        return jsonify({"response": bot_response})

    except Exception as e:
        print(f"Error in /api/chat: {e}")
        # 이 단계에서 rollback은 봇 응답 저장 실패 시에만 영향을 줌
        if conn:
            conn.rollback()
        return jsonify({"error": "서버 처리 중 오류가 발생했습니다."}), 500
    finally:
        if conn:
            conn.close()

# C:/Users/zxzx0/Desktop/chatbot/untitled3/AIchat/app.py

@app.route("/api/new_chat", methods=["POST"])
def new_chat():
    """새로운 대화를 시작하고, 새 세션 ID를 함께 반환하는 API"""
    user_id = session['user_id']
    bot_type = request.json.get('bot_type')
    conn = get_db_conn()
    try:
        # 기존 활성 세션을 비활성화
        conn.execute('UPDATE chat_sessions SET is_active = 0 WHERE user_id = ? AND bot_type = ? AND is_active = 1', (user_id, bot_type))

        # 새로운 세션 생성
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_sessions (user_id, bot_type, session_name, is_active) VALUES (?, ?, ?, 1)",
            (user_id, bot_type, "새로운 대화")
        )
        new_session_id = cursor.lastrowid # <--- 새로 생성된 세션 ID

        # 환영 메시지 추가
        welcome_message = random.choice(PERSONAS[bot_type]["greetings"])
        new_history = [{"role": "assistant", "content": welcome_message}]
        conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (new_session_id, "assistant", welcome_message)
        )
        conn.commit()

        # [핵심 수정] 새 세션 ID를 history와 함께 반환
        return jsonify({"history": new_history, "session_id": new_session_id})
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

@app.route("/api/like_message", methods=["POST"])
def like_message():
    """메시지를 '좋아요' 목록에 저장하는 API"""
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

@app.route("/api/favorites", methods=["GET"])
def get_favorites():
    """저장된 메시지 목록을 반환하는 API"""
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
    """저장된 메시지를 삭제하는 API"""
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "로그인이 필요합니다."}), 401
    message_id = request.json.get("id")
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

# --- 5. 앱 실행 ---
if __name__ == "__main__":
    app.run(debug=True, port=5001)