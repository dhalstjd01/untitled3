import sqlite3

print("--- 데이터베이스 내용 확인 시작 ---")

try:
    # 데이터베이스 연결
    conn = sqlite3.connect('chatbot_likes.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n[1] 'messages' 테이블의 최근 10개 내용을 출력합니다.")
    cursor.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 10")
    messages = cursor.fetchall()

    if not messages:
        print("-> 'messages' 테이블에 데이터가 없습니다.")
    else:
        print("ID | Session | Role      | Emotion | Content")
        print("----------------------------------------------------------")
        for msg in messages:
            # emotion이 None일 경우 '없음'으로 표시
            emotion_str = msg['emotion'] if msg['emotion'] is not None else '없음'
            # 내용이 길 경우 일부만 표시
            content_str = (msg['content'][:30] + '...') if len(msg['content']) > 30 else msg['content']
            print(f"{msg['id']:<2} | {msg['session_id']:<7} | {msg['role']:<9} | {emotion_str:<7} | {content_str}")

    print("\n[2] 'chat_sessions' 테이블의 내용을 출력합니다.")
    cursor.execute("SELECT * FROM chat_sessions ORDER BY id DESC LIMIT 5")
    sessions = cursor.fetchall()

    if not sessions:
        print("-> 'chat_sessions' 테이블에 데이터가 없습니다.")
    else:
        print("ID | UserID | Bot | PHQ Done | Stage | Active | Name")
        print("----------------------------------------------------------")
        for s in sessions:
            print(f"{s['id']:<2} | {s['user_id']:<6} | {s['bot_type']:<3} | {s['phq_completed']:<8} | {s['user_stage']:<5} | {s['is_active']:<6} | {s['session_name']}")


except sqlite3.OperationalError as e:
    print(f"\n❌ 오류 발생: {e}")
    print("-> 'messages' 테이블이나 'emotion' 컬럼이 존재하지 않을 수 있습니다.")
    print("-> 데이터베이스 파일을 삭제하고 'python init_db.py'를 다시 실행해보세요.")
except Exception as e:
    print(f"\n❌ 알 수 없는 오류 발생: {e}")
finally:
    if 'conn' in locals() and conn:
        conn.close()

print("\n--- 확인 완료 ---")