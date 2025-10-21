import torch

# GPU 사용 가능 여부 체크
is_available = torch.cuda.is_available()

print(f"PyTorch 버전: {torch.__version__}")
print(f"GPU 사용 가능: {is_available}")

if is_available:
    print(f"GPU 개수: {torch.cuda.device_count()}")
    print(f"현재 GPU 이름: {torch.cuda.get_device_name(0)}")
else:
    print("------------------------------------------------")
    print("GPU를 사용할 수 없습니다. CPU 버전의 PyTorch가 설치된 것 같습니다.")
    print("아래 '2단계'를 진행하여 GPU 버전의 PyTorch를 설치해주세요.")
    print("------------------------------------------------")
