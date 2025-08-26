# D:/MS/AIChatBot/AIchat/chatbot.py

import os
from openai import OpenAI
# emotion_analyzer.py 파일이 프로젝트 폴더에 있다고 가정합니다.
from emotion_analyzer import EmotionAnalyzer
from prompts import SCENARIOS

class Chatbot:
    def __init__(self):
        """챗봇 초기화: OpenAI 클라이언트와 감정 분석기를 준비합니다."""
        try:
            self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            if not self.client.api_key:
                raise ValueError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
        except Exception as e:
            print(f"❌ OpenAI 클라이언트 초기화 실패: {e}")
            self.client = None

        self.emotion_analyzer = EmotionAnalyzer()

    def get_response_and_emotion(self, user_input: str, persona_prompt: str, history: list, stage: int) -> tuple[str, str]:
        """
        사용자의 상태(stage)에 맞는 대화 전략을 적용하여 응답을 생성하고,
        분석된 감정을 함께 반환합니다.
        """
        if not self.client:
            return "죄송해요, OpenAI 서비스에 연결할 수 없어요. API 키 설정을 확인해주세요.", "중립"

        # 1. 감정 분석
        emotion = self.emotion_analyzer.analyze_emotion(user_input)

        # 2. PHQ-9 단계에 따른 대화 전략 가져오기
        stage_info = SCENARIOS.get(stage, SCENARIOS[1])
        strategy = stage_info["strategy"]

        # 3. 최종 시스템 프롬프트 조립
        final_system_prompt = (
            f"### 현재 대화 전략 (사용자 상태 단계: {stage})\n"
            f"{strategy}\n\n"
            f"---\n\n"
            f"{persona_prompt}"
        )

        # 4. API에 보낼 메시지 목록 생성 (사용자의 마지막 메시지 포함)
        messages_for_api = [
                               {"role": "system", "content": final_system_prompt}
                           ] + history

        try:
            # 5. OpenAI API 호출
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages_for_api,
                temperature=0.8,
            )
            bot_response = response.choices[0].message.content
            return bot_response, emotion  # 답변과 감정을 튜플로 반환

        except Exception as e:
            print(f"❌ OpenAI API 호출 중 오류 발생: {e}")
            return "죄송해요, 지금은 제 생각을 정리하기가 조금 힘드네요. 다시 말씀해주시겠어요?", "중립"

    def get_response(self, user_input: str, persona_prompt: str, history: list, stage: int) -> str:
        """기존 get_response는 하위 호환성을 위해 유지합니다."""
        bot_response, _ = self.get_response_and_emotion(user_input, persona_prompt, history, stage)
        return bot_response