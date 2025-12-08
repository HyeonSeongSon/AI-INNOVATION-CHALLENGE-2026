import paddle

print("=" * 60)
print("PaddlePaddle GPU 환경 확인")
print("=" * 60)

# GPU 사용 가능 여부
is_gpu_available = paddle.is_compiled_with_cuda()
print(f"\n✓ GPU 사용 가능: {is_gpu_available}")

if is_gpu_available:
    # GPU 개수
    gpu_count = paddle.device.cuda.device_count()
    print(f"✓ GPU 개수: {gpu_count}")
    
    # CUDA 버전
    cuda_version = paddle.version.cuda()
    print(f"✓ CUDA 버전: {cuda_version}")
    
    # cuDNN 버전
    cudnn_version = paddle.version.cudnn()
    print(f"✓ cuDNN 버전: {cudnn_version}")
    
    # GPU 이름
    paddle.device.set_device('gpu:0')
    print(f"✓ 현재 디바이스: {paddle.get_device()}")
    
    print("\n🎉 GPU 설정 완료!")
else:
    print("\n❌ GPU를 사용할 수 없습니다.")
    print("CPU 버전이 설치되었거나 CUDA 설정에 문제가 있습니다.")