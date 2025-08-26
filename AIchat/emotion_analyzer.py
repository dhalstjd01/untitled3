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

    def analyze_emotion(self, text: str) -> str:
        if not self.classifier:
            return "분석실패"

        try:
            result = self.classifier(text)
            print("분석 원본 결과:", result)  # 감정 분석 원본 결과만 출력

            label = result[0]['label']
            return label  # 라벨 그대로 반환
        except Exception as e:
            print(f"❌ 감정 분석 중 오류: {e}")
            return "분석실패"


