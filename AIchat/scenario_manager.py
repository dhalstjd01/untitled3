# C:/.../AIchat/scenario_manager.py

import random

class ScenarioManager:
    """
    사용자의 상태(stage)와 감정(emotion)에 따라
    미리 정의된 시나리오 응답을 관리하고 반환하는 클래스입니다.
    """
    def __init__(self, scenarios: dict):
        """
        ScenarioManager를 초기화합니다.
        :param scenarios: prompts.py에 정의된 SCENARIOS 딕셔너리
        """
        self.scenarios = scenarios
        print("✅ 시나리오 매니저 초기화 성공")

    def get_response(self, stage: str, emotion: str) -> str or None:
        """
        주어진 stage와 emotion에 해당하는 시나리오 응답을 반환합니다.
        """
        try:
            stage_scenarios = self.scenarios.get(str(stage))
            if not stage_scenarios:
                return None

            emotion_responses = stage_scenarios.get(emotion)
            if not emotion_responses:
                return None

            return random.choice(emotion_responses)

        except Exception as e:
            print(f"⚠️ 시나리오 응답을 가져오는 중 오류 발생: {e}")
            return None