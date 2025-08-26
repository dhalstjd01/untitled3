# test_connection.py
from transformers import pipeline

def run_test():
    """
    Hugging Face 서버와의 연결을 테스트하기 위한 최소한의 코드.
    가장 유명하고 기본적인 모델 중 하나를 다운로드 시도합니다.
    """
    try:
        model_name = "bert-base-multilingual-cased"
        print(f"---[ 연결 테스트 시작 ]---")
        print(f"'{model_name}' 모델 다운로드를 시도합니다...")

        # 이 코드가 성공하면, 네트워크와 라이브러리는 정상입니다.
        pipeline('fill-mask', model=model_name)

        print("\n[ 성공! ]")
        print("Hugging Face 서버와 정상적으로 통신했습니다.")
        print("네트워크와 라이브러리 설치에는 문제가 없습니다.")

    except Exception as e:
        print("\n[ 실패! ]")
        print("Hugging Face 서버와 통신하는 데 실패했습니다.")
        print("이것이 모든 문제의 근본적인 원인입니다.")
        print("\n---[ 발생한 오류 ]---")
        print(e)

    finally:
        print("---[ 연결 테스트 종료 ]---")

if __name__ == "__main__":
    run_test()