# C:/.../AIchat/chatbot.py

import os
from openai import OpenAI
from emotion_analyzer import EmotionAnalyzer
from scenario_manager import ScenarioManager
from prompts import SCENARIOS, PHQ9_QUESTIONS

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

    # ⭐ [핵심 추가] 사용자의 자연어 답변을 분석하여 PHQ-9 점수로 변환하는 함수
    def analyze_phq_answer(self, user_answer: str, question_index: int) -> int:
        """사용자의 답변을 분석하여 0, 1, 2, 3 중 하나의 점수를 반환합니다."""
        if not self.client: return -1 # 오류 시 -1 반환

        question_ho = PHQ9_QUESTIONS[question_index]["question_ho"]

        system_prompt = f"""
        당신은 사용자의 답변을 분석하여 PHQ-9 설문의 점수를 매기는 정밀한 분석가입니다.
        현재 질문은 "{question_ho}" 입니다.
        사용자의 답변이 지난 2주 동안의 빈도를 얼마나 나타내는지 판단하여, 아래 4가지 중 해당하는 숫자를 단 하나만 반환해야 합니다.
        
        - 0: '전혀 없음' (없었다, 아니다, 괜찮다 등 부정적 답변)
        - 1: '며칠 동안' (가끔, 조금, 한두 번, 주말에만 등 간헐적 빈도)
        - 2: '일주일 이상 (절반 이상)' (자주, 꽤 많이, 대부분 등 높은 빈도)
        - 3: '거의 매일' (항상, 매일, 늘, 요즘 계속 등 매우 높은 빈도)

        오직 숫자 0, 1, 2, 3 중 하나만 출력하고, 다른 어떤 말도 덧붙이지 마세요.

        [예시]
        답변: "아니 전혀." -> 출력: 0
        답변: "가끔 그랬던 것 같아" -> 출력: 1
        답변: "응 요즘 자주 그래" -> 출력: 2
        답변: "매일 같이 그래" -> 출력: 3
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_answer}
                ],
                temperature=0,
                max_tokens=5
            )

            result_text = response.choices[0].message.content.strip()
            if result_text in ["0", "1", "2", "3"]:
                return int(result_text)
            else:
                print(f"⚠️ PHQ-9 답변 분석 실패: 예상치 못한 결과 '{result_text}'")
                return -1
        except Exception as e:
            print(f"❌ PHQ-9 답변 분석 API 호출 오류: {e}")
            return -1

    def get_response_and_emotion(self, user_input: str, persona_prompt: str, history: list, stage: str, pre_analyzed_emotion: str = None) -> tuple[str, str]:
        if not self.client:
            return "죄송해요, OpenAI 서비스에 연결할 수 없어요. API 키 설정을 확인해주세요.", "분석실패"

        detected_emotion_label = "분석실패"
        emotion_display_log = "분석실패"

        if pre_analyzed_emotion:
            detected_emotion_label = pre_analyzed_emotion
            emotion_display_log = pre_analyzed_emotion
        elif self.emotion_analyzer:
            emotion_result = self.emotion_analyzer.analyze_emotion(user_input)
            if emotion_result:
                detected_emotion_label = emotion_result['label']
                emotion_display_log = f"{emotion_result['label']} (Score: {emotion_result['score']:.2f})"

        if self.scenario_manager:
            scenario_response = self.scenario_manager.get_response(stage, detected_emotion_label)
            if scenario_response:
                print(f"ℹ️ 시나리오 응답 반환 (Stage: {stage}, Emotion: {emotion_display_log})")
                return scenario_response, detected_emotion_label

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
                    bot_response = "음... 해당 주제에 대해서는 답변하기 조금 어려울 것 같아요. 다른 이야기를 해볼까요?"
                return bot_response, detected_emotion_label
            else:
                return "죄송해요, 지금은 답변을 생성하기가 어렵네요. 잠시 후 다시 시도해주세요.", detected_emotion_label
        except Exception as e:
            print(f"❌ OpenAI API 호출 오류: {e}")
            return "미안해요, 지금은 답변을 생성하기 어려워요.", detected_emotion_label

    def get_response(self, user_input: str, persona_prompt: str, history: list, stage: str) -> str:
        bot_response, _ = self.get_response_and_emotion(user_input, persona_prompt, history, stage)
        return bot_response