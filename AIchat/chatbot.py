# chatbot.py

import os
from dotenv import load_dotenv
import openai

from emotion_analyzer import EmotionAnalyzer
from prompts import SCENARIOS

class Chatbot:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError("❌ OPENAI_API_KEY를 찾을 수 없습니다. .env 파일에 키를 설정해주세요.")

        try:
            self.client = openai.OpenAI(api_key=api_key)
            print("✅ OpenAI 클라이언트 초기화 성공")
        except Exception as e:
            print(f"❌ OpenAI 클라이언트 초기화 중 오류 발생: {e}")
            raise

        try:
            self.emotion_analyzer = EmotionAnalyzer()
            print("✅ 감정 분석기 로딩 성공")
        except Exception as e:
            print(f"❌ 감정 분석기 로딩 실패: {e}")
            print("⚠️ 감정 분석 기능 없이 챗봇을 실행합니다. (emotion_analyzer.py 또는 모델 파일 확인 필요)")
            self.emotion_analyzer = None

    def get_response_and_emotion(self, user_input: str, persona_prompt: str, history: list, stage: int) -> tuple[str, str]:
        emotion = "분석 불가"
        if self.emotion_analyzer:
            try:
                emotion = self.emotion_analyzer.analyze_emotion(user_input)
            except Exception as e:
                print(f"⚠️ 감정 분석 중 오류 발생: {e}")

        # ⭐ [수정] str() 변환을 제거하여 숫자(int) 키를 그대로 사용합니다.
        stage_info = SCENARIOS.get(stage, SCENARIOS.get(1))
        strategy = stage_info.get("strategy", "사용자의 말을 주의 깊게 듣고 공감해주세요.")

        final_system_prompt = (
            f"### 현재 대화 전략 (사용자 상태 단계: {stage})\n"
            f"{strategy}\n\n"
            f"---\n\n"
            f"### 챗봇 페르소나\n"
            f"{persona_prompt}"
        )

        messages_for_api = [
                               {"role": "system", "content": final_system_prompt}
                           ] + history

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages_for_api,
                temperature=0.8,
                max_tokens=1024,
            )
            bot_response = response.choices[0].message.content
            return bot_response, emotion

        except openai.APIError as e:
            print(f"❌ OpenAI API 오류 발생: {e}")
            return "죄송해요, 지금 OpenAI 서비스에 문제가 있는 것 같아요. 잠시 후 다시 시도해주세요.", emotion
        except Exception as e:
            print(f"❌ 응답 생성 중 알 수 없는 오류 발생: {e}")
            return "죄송해요, 지금은 제 생각을 정리하기가 조금 힘드네요. 다시 말씀해주시겠어요?", emotion

    def get_response(self, user_input: str, persona_prompt: str, history: list, stage: int) -> str:
        bot_response, _ = self.get_response_and_emotion(user_input, persona_prompt, history, stage)
        return bot_response