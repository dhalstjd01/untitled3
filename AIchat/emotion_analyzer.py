# C:/.../AIchat/emotion_analyzer.py

from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

class EmotionAnalyzer:
    def __init__(self):
        try:
            model_name = "./kobert-emotion-final"
            print(f"🔄 감정 분석기 '{model_name}' 로딩 중...")

            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForSequenceClassification.from_pretrained(model_name)

            self.classifier = pipeline("text-classification", model=model, tokenizer=tokenizer)
            print("✅ 감정 분석기 로딩 완료!")
        except Exception as e:
            print(f"❌ 감정 분석기 로딩 실패: {e}")
            self.classifier = None

    def analyze_emotion(self, text: str) -> dict or None:
        """
        주어진 텍스트의 감정을 분석하여 라벨과 점수가 포함된 딕셔너리를 반환합니다.
        분석 실패 시 None을 반환합니다.
        """
        if not self.classifier:
            return None

        try:
            result = self.classifier(text)
            # ⭐ [수정] 결과가 있을 경우, 라벨과 점수가 담긴 첫 번째 딕셔너리를 그대로 반환
            if result:
                return result[0]
            return None
        except Exception as e:
            print(f"❌ 감정 분석 중 오류: {e}")
            return None