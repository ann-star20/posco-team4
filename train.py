import os
import shutil
import torch
from ultralytics import YOLO

# ---------------------------------------------------------
# [환경 설정 플래그] 코랩: True / 로컬 PC: False
# ---------------------------------------------------------
IS_COLAB = False

if IS_COLAB:
    from google.colab import drive
    if not os.path.exists('/content/drive'):
        drive.mount('/content/drive')
    
    # 내 드라이브의 실제 마운트 경로
    DRIVE_SAVE_DIR = '/content/drive/MyDrive/posco_vision/YOLO_results'
    # 학습은 코랩 초고속 로컬 SSD 디스크에서 진행
    LOCAL_PROJECT_PATH = '/content/YOLO_results'
    # 코랩 디바이스 설정 (GPU 지원 시 0, 없으면 cpu)
    DEVICE = 0 if torch.cuda.is_available() else 'cpu'
else:
    # 로컬 PC 환경 경로 (현재 스크립트 위치 기준 절대 경로)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    LOCAL_PROJECT_PATH = os.path.join(BASE_DIR, "YOLO_results")
    DRIVE_SAVE_DIR = LOCAL_PROJECT_PATH
    # 💥 핵심: 로컬 PC의 GPU(CUDA) 가용 여부를 자동 감지하여 cpu/0 결정
    DEVICE = 0 if torch.cuda.is_available() else 'cpu'

def train_and_sync_model(stage_type='part', model_version='v4-hsv-93012'):
    # 절대 경로 기반 데이터셋 yaml 설정
    if IS_COLAB:
        yaml_path = f"/content/drive/MyDrive/posco_vision/datasets/data_{stage_type}.yaml"
    else:
        yaml_path = os.path.join(BASE_DIR, "datasets", f"data_{stage_type}.yaml")

    model_name = f"mosfet_{stage_type}_{model_version}"
    
    print(f"\n==================================================")
    print(f"🚀 [{stage_type.upper()} 모델 / Device: {DEVICE}] 학습 시작...")
    print(f"==================================================\n")
    
    model = YOLO("yolov8m-seg.pt")
    
    results = model.train(
        data=yaml_path,
        epochs=150,
        imgsz=800,
        batch=8,
        device=DEVICE,  # 👈 자동 판별된 안전한 Device 사용 ('cpu' 또는 0)
        patience=50,
        overlap_mask=True,
        # stage_type에 따른 하이퍼파라미터 분기
        cls=1.5 if stage_type == 'defect' else 0.5, # 결함 모델은 Class Loss 강화
        box=7.5,
        scale=0.3,
        mosaic=0.0 if stage_type == 'defect' else 1.0, # 결함 모델은 Mosaic OFF
        degrees=10.0,
        fliplr=0.5,
        flipud=0.0,
        exist_ok=True,
        project=LOCAL_PROJECT_PATH,
        name=model_name,
    )
    
    # ---------------------------------------------------------
    # 💥 코랩 전용 구글 드라이브 동기화 (로컬 PC일 때는 자동 스킵)
    # ---------------------------------------------------------
    if IS_COLAB:
        local_weight_dir = os.path.join(LOCAL_PROJECT_PATH, model_name, "weights")
        drive_weight_dir = os.path.join(DRIVE_SAVE_DIR, model_name, "weights")
        
        os.makedirs(drive_weight_dir, exist_ok=True)
        
        print(f"\n📂 [{stage_type.upper()}] 구글 드라이브로 가중치 파일 안심 복사 중...")
        for pt_file in ["best.pt", "last.pt"]:
            src = os.path.join(local_weight_dir, pt_file)
            dst = os.path.join(drive_weight_dir, pt_file)
            if os.path.exists(src):
                shutil.copy2(src, dst)
                print(f"  ✅ 복사 완료: {pt_file} -> {dst}")
        
        # 구글 드라이브 강제 캐시 비우기 (Sync)
        os.system("sync")
        print(f"🎉 [{stage_type.upper()}] 구글 드라이브 동기화 완료!")
    else:
        print(f"🎉 [{stage_type.upper()}] 로컬 저장 완료: {os.path.join(LOCAL_PROJECT_PATH, model_name)}")

if __name__ == "__main__":
    MODEL_VER = 'v0'

    # 1️⃣ [Stage 1] 부품 탐지 모델 학습
    train_and_sync_model(stage_type='part', model_version=MODEL_VER)

    # 2️⃣ [Stage 2] 결함 탐지 모델 학습 (필요 시 주석 해제하여 함께 실행 가능)
    # train_and_sync_model(stage_type='defect', model_version=MODEL_VER)

    print("\n🎉 모든 지정 학습 작업이 완료되었습니다!")