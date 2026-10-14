import os
import glob
from datetime import datetime
import cv2
import numpy as np
from ultralytics import YOLO
from ultralytics.utils.plotting import Annotator

# ---------------------------------------------------------
# [환경 설정 플래그] 코랩: True / 로컬 PC: False
# ---------------------------------------------------------
IS_COLAB = False

if IS_COLAB:
    from google.colab import drive
    if not os.path.exists('/content/drive'):
        drive.mount('/content/drive')
    BASE_DIR = '/content/drive/MyDrive/posco_vision'
    INFER_DEVICE = 'cpu'  # 코랩 무료 플랜 추론 시 CPU 권장 (GPU 필요 시 0)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    INFER_DEVICE = 'cpu'      # 로컬 GPU 환경일 경우 0, 없으면 'cpu'

PROJECT_PATH = os.path.join(BASE_DIR, "YOLO_results")

PART_CLASS_NAMES = {
    0: "body", 1: "lead", 2: "tab", 
    # 3: "text_model", 4: "text_lot", 5: "text_id"
}

DEFECT_CLASS_NAMES = {
    0: "crash", 1: "scratch", 2: "bend"
}

# ---------------------------------------------------------
# 색상 정의 (OpenCV BGR 포맷)
# ---------------------------------------------------------
COLOR_PART = (255, 128, 0)   # 부품 탐지: 파란색/청록색 계열 (Cyan-Blue)
COLOR_DEFECT = (0, 0, 255)   # 결함 탐지: 선명한 빨간색 (Red)

def get_weight_path(model_name):
    best_path = os.path.join(PROJECT_PATH, model_name, "weights", "best.pt")
    last_path = os.path.join(PROJECT_PATH, model_name, "weights", "last.pt")

    if os.path.exists(best_path):
        return best_path
    elif os.path.exists(last_path):
        print(f"⚠️️ '{model_name}'의 best.pt가 없어 last.pt를 사용합니다.")
        return last_path
    else:
        raise FileNotFoundError(f"❌ 가중치 파일을 찾을 수 없습니다: {best_path}")

def draw_transparent_overlay(img_bgr, results, class_names, color, is_defect=False):
    """
    YOLO Annotator를 활용하여 마스크 영역의 반투명도(Alpha)를 유지하면서
    원하는 지정 색상(부품: 파랑 / 결함: 빨강)으로 시각화합니다.
    """
    annotator = Annotator(img_bgr, line_width=3 if is_defect else 2)

    # 1. 세그멘테이션 마스크 시각화 (반투명 처리)
    if results.masks is not None:
        clss = results.boxes.cls.cpu().numpy()
        masks = results.masks.data.cpu().numpy()
        img_h, img_w = img_bgr.shape[:2]

        for mask in masks:
            # 원본 크기로 마스크 리사이즈
            mask_resized = cv2.resize(mask, (img_w, img_h)) > 0.5
            
            # 마스크 픽셀 부분만 알파 블렌딩 (투명도 35% 적용)
            colored_mask = np.zeros_like(img_bgr, dtype=np.uint8)
            colored_mask[mask_resized] = color
            
            # 원본 이미지에 반투명 합성
            img_bgr = cv2.addWeighted(img_bgr, 1.0, colored_mask, 0.35, 0)

        # 갱신된 배경 이미지를 Annotator에 다시 전달
        annotator.im = img_bgr

    # 2. 바운딩 박스 및 라벨 작성
    if results.boxes is not None:
        for box in results.boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            xyxy = box.xyxy[0].cpu().numpy()

            label_name = class_names.get(cls_id, f"cls_{cls_id}")
            label = f"{'⚠️ ' if is_defect else ''}{label_name} {conf:.2f}"

            annotator.box_label(xyxy, label, color=color)

    return annotator.result()

def run_2stage_inference(part_model_name, defect_model_name, custom_img_path=None):
    part_weight = get_weight_path(part_model_name)
    defect_weight = get_weight_path(defect_model_name)

    print(f"🔍 [Stage 1] 부품 모델 가중치: {part_weight}")
    print(f"🔍 [Stage 2] 결함 모델 가중치: {defect_weight}\n")

    part_model = YOLO(part_weight)
    defect_model = YOLO(defect_weight)

    test_images = []
    if custom_img_path:
        if os.path.exists(custom_img_path):
            test_images.append(custom_img_path)
        else:
            print(f"❌ 지정한 이미지 파일이 없습니다: {custom_img_path}")
            return
    else:
        test_dir = os.path.join(BASE_DIR, "datasets", "test_raw")
        os.makedirs(test_dir, exist_ok=True)
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.PNG', '*.JPEG']:
            test_images.extend(glob.glob(os.path.join(test_dir, ext)))

        if not test_images:
            print(f"⚠️ 'datasets/test_raw' 폴더에 테스트할 이미지가 없습니다: {test_dir}")
            return

    save_dir = os.path.join(BASE_DIR, "inference_results_2stage")
    os.makedirs(save_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"🚀 [환경: {'COLAB' if IS_COLAB else 'LOCAL'}] 총 {len(test_images)}개 이미지 추론 진행 중...\n")

    for img_path in test_images:
        file_name = os.path.basename(img_path)
        name_only, ext_only = os.path.splitext(file_name)

        try:
            orig_img_bgr = cv2.imread(img_path)
            if orig_img_bgr is None:
                print(f"❌ 이미지 읽기 실패: {img_path}")
                continue

            # 추론
            part_res = part_model.predict(source=orig_img_bgr, conf=0.35, iou=0.45, device=INFER_DEVICE)[0]
            defect_res = defect_model.predict(source=orig_img_bgr, conf=0.20, iou=0.35, device=INFER_DEVICE)[0]
        except Exception as e:
            print(f"❌ 추론 실패 ({file_name}): {e}")
            continue

        print(f"📸 [결과 요약] 파일명: {file_name}")
        print("  🔹 [부품 탐지]")
        for box in part_res.boxes:
            cls_id, conf = int(box.cls[0].item()), float(box.conf[0].item())
            print(f"     - [{PART_CLASS_NAMES.get(cls_id, cls_id)}] {conf:.2f}")

        print("  🔴 [결함 탐지]")
        for box in defect_res.boxes:
            cls_id, conf = int(box.cls[0].item()), float(box.conf[0].item())
            print(f"     - ⚠️ [{DEFECT_CLASS_NAMES.get(cls_id, cls_id)}] {conf:.2f}")

        # 1) 원본 이미지 위에 [부품] 마스크(투명도 35%) 및 박스(파란색) 시각화
        combined_bgr = draw_transparent_overlay(orig_img_bgr, part_res, PART_CLASS_NAMES, COLOR_PART, is_defect=False)
        
        # 2) 1단계 시각화 결과 위에 [결함] 마스크(투명도 35%) 및 박스(빨간색) 덮어 씌우기
        combined_bgr = draw_transparent_overlay(combined_bgr, defect_res, DEFECT_CLASS_NAMES, COLOR_DEFECT, is_defect=True)

        # 결과 저장
        save_path = os.path.join(save_dir, f"res2s_{timestamp}_{name_only}{ext_only}")
        cv2.imwrite(save_path, combined_bgr)
        print(f"  💾 저장 완료: {save_path}\n")

    print(f"🎉 모든 추론 완료! 결과 저장 위치: '{save_dir}'")

if __name__ == "__main__":
    run_2stage_inference(
        part_model_name='mosfet_part_v4-hsv-93012',
        defect_model_name='mosfet_defect_v4-hsv-93012'
    )