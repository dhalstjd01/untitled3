# C:/.../AIchat/chatbot.py

import os
from openai import OpenAI
from emotion_analyzer import EmotionAnalyzer
from scenario_manager import ScenarioManager
from prompts import SCENARIOS

class Chatbot:
    def __init__(self):
        """챗봇 초기화: OpenAI 클라이언트, 감정 분석기, 시나리오 매니저를 준비합니다."""
        try:
            self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            if not self.client.api_key:
                raise ValueError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
            print("✅ OpenAI 클라이언트 초기화 성공")
        except Exception as e:
            print(f"❌ OpenAI 클라이언트 초기화 실패: {e}")
            self.client = None

        try:
            self.emotion_analyzer = EmotionAnalyzer()
            print("✅ 감정 분석기 로딩 성공")
        except Exception as e:
            print(f"❌ 감정 분석기 로딩 실패: {e}")
            self.emotion_analyzer = None

        try:
            self.scenario_manager = ScenarioManager(SCENARIOS)
        except Exception as e:
            print(f"❌ 시나리오 매니저 초기화 실패: {e}")
            self.scenario_manager = None

    def get_response_and_emotion(self, user_input: str, persona_prompt: str, history: list, stage: str, pre_analyzed_emotion: str = None) -> tuple[str, str]:
        """
        사용자 입력과 대화 기록을 바탕으로 챗봇의 응답과 사용자 감정을 반환합니다.
        """
        if not self.client:
            return "죄송해요, OpenAI 서비스에 연결할 수 없어요. API 키 설정을 확인해주세요.", "분석실패"

        # ⭐ [수정] 감정 분석 로직 변경
        detected_emotion_label = "분석실패"
        emotion_display_log = "분석실패" # 터미널 출력용 변수

        if pre_analyzed_emotion:
            detected_emotion_label = pre_analyzed_emotion
            emotion_display_log = pre_analyzed_emotion
        elif self.emotion_analyzer:
            emotion_result = self.emotion_analyzer.analyze_emotion(user_input)
            if emotion_result:
                detected_emotion_label = emotion_result['label']
                # 터미널에 출력할 상세 정보 생성 (소수점 2자리까지)
                emotion_display_log = f"{emotion_result['label']} (Score: {emotion_result['score']:.2f})"

        # 시나리오 기반 응답 생성 시도 (라벨만 사용)
        if self.scenario_manager:
            scenario_response = self.scenario_manager.get_response(stage, detected_emotion_label)
            if scenario_response:
                print(f"ℹ️ 시나리오 응답 반환 (Stage: {stage}, Emotion: {emotion_display_log})")
                return scenario_response, detected_emotion_label

        # LLM을 통한 일반 응답 생성 (라벨과 로그용 정보를 모두 사용)
        print(f"ℹ️ LLM 응답 생성 (Stage: {stage}, Emotion: {emotion_display_log})")
        system_prompt = f"{persona_prompt}\n너는 사용자의 현재 감정 상태({detected_emotion_label})와 우울 단계({stage}단계)를 이해하고, 그에 맞춰 공감하고 위로하는 답변을 생성해야 해."

        messages = [{"role": "system", "content": system_prompt}] + history

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=150
            )

            if response.choices:
                bot_response = response.choices[0].message.content
                if response.choices[0].finish_reason == 'content_filter':
                    print("⚠️ OpenAI 안전 필터에 의해 답변이 차단되었습니다.")
                    bot_response = "음... 해당 주제에 대해서는 답변하기 조금 어려울 것 같아요. 다른 이야기를 해볼까요?"
                return bot_response, detected_emotion_label
            else:
                print("⚠️ OpenAI로부터 응답을 받았으나, choices 리스트가 비어있습니다.")
                return "죄송해요, 지금은 답변을 생성하기가 어렵네요. 잠시 후 다시 시도해주세요.", detected_emotion_label

        except Exception as e:
            print(f"❌ OpenAI API 호출 오류: {e}")
            return "미안해요, 지금은 답변을 생성하기 어려워요.", detected_emotion_label

    def get_response(self, user_input: str, persona_prompt: str, history: list, stage: str) -> str:
        bot_response, _ = self.get_response_and_emotion(user_input, persona_prompt, history, stage)
        return bot_response