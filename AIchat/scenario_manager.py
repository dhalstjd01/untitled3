class ScenarioManager:
    def __init__(self, scenarios: dict):
        """시나리오 딕셔너리로 매니저를 초기화합니다."""
        self.scenarios = scenarios

    def get_response(self, stage: int, emotion: str) -> str or None:
        """
        사용자의 단계(stage)와 감정(emotion)에 맞는 시나리오 응답을 반환합니다.
        적절한 응답이 없으면 None을 반환합니다.
        """
        # stage 키가 존재하는지 확인
        if stage in self.scenarios:
            # 해당 stage에서 emotion 키가 존재하는지 확인
            if emotion in self.scenarios[stage]:
                return self.scenarios[stage][emotion]
        # 적절한 시나리오가 없는 경우
        return None