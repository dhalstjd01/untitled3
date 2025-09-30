import os
from openai import OpenAI
from emotion_analyzer import EmotionAnalyzer
# --- [수정] ScenarioManager와 SCENARIOS를 import 합니다. ---
from scenario_manager import ScenarioManager
from prompts import SCENARIOS

class Chatbot:
    def __init__(self):
        """챗봇 초기화: OpenAI 클라이언트, 감정 분석기, 시나리오 매니저를 준비합니다."""
        try:
            self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            if not self.client.api_key:
                raise ValueError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
        except Exception as e:
            print(f"❌ OpenAI 클라이언트 초기화 실패: {e}")
            self.client = None

        self.emotion_analyzer = EmotionAnalyzer()
        # --- [수정] ScenarioManager를 초기화하고 self.scenario_manager에 할당합니다!. ---
        self.scenario_manager = ScenarioManager(SCENARIOS)

    def get_response_and_emotion(self, user_input: str, persona_prompt: str, history: list, stage: int, pre_analyzed_emotion: str = None):
        """
        사용자 입력과 대화 기록을 바탕으로 챗봇의 응답과 사용자 감정을 반환합니다.
        만약 감정이 미리 분석되었다면, 그 값을 사용하고 재분석을 건너뜁니다.
        """
        # pre_analyzed_emotion 값이 있으면 그대로 사용하고, 없으면 새로 분석합니다.
        detected_emotion = pre_analyzed_emotion
        if detected_emotion is None:
            detected_emotion = self.emotion_analyzer.analyze_emotion(user_input)

        # 시나리오 기반 응답 생성
        scenario_response = self.scenario_manager.get_response(stage, detected_emotion)
        if scenario_response:
            return scenario_response, detected_emotion

        # 시나리오가 없을 경우, LLM을 통한 일반 응답 생성
        system_prompt = f"{persona_prompt}\n너는 사용자의 현재 감정 상태({detected_emotion})와 우울 단계({stage}단계)를 이해하고, 그에 맞춰 공감하고 위로하는 답변을 생성해야 해."

        messages = [{"role": "system", "content": system_prompt}] + history

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=150
            )
            bot_response = response.choices[0].message.content
            return bot_response, detected_emotion
        except Exception as e:
            print(f"❌ OpenAI API 호출 오류: {e}")
            return "미안해요, 지금은 답변을 생성하기 어려워요.", detected_emotion

    def get_response(self, user_input: str, persona_prompt: str, history: list, stage: int) -> str:
        """기존 get_response는 하위 호환성을 위해 유지합니다."""
        bot_response, _ = self.get_response_and_emotion(user_input, persona_prompt, history, stage)
        return bot_response