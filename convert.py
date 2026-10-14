import os
import json
import glob
import shutil
import random
from PIL import Image

IS_COLAB = False

if IS_COLAB:
    from google.colab import drive
    if not os.path.exists('/content/drive'):
        drive.mount('/content/drive')
    BASE_DIR = '/content/drive/MyDrive/posco_vision'
else:
    notebook_path = globals().get("__vsc_ipynb_file__")
    if notebook_path:
        BASE_DIR = os.path.dirname(os.path.abspath(notebook_path))
    elif "__file__" in globals():
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    else:
        BASE_DIR = os.getcwd()
        while not os.path.isdir(os.path.join(BASE_DIR, "datasets")):
            parent_dir = os.path.dirname(BASE_DIR)
            if parent_dir == BASE_DIR:
                break
            BASE_DIR = parent_dir

DATASETS_DIR = os.path.join(BASE_DIR, "datasets")
JSON_RAW_DIR = os.path.join(DATASETS_DIR, "json_raw")
if not os.path.isdir(JSON_RAW_DIR):
    raise FileNotFoundError(f"JSON dataset directory not found: {JSON_RAW_DIR}")

# Stage별 클래스 매핑 (0부터 시작)
PART_CLASS_MAPPING = {
    "body": 0, "lead": 1, "tab": 2
}

DEFECT_CLASS_MAPPING = {
    "scratch": 0, "crash": 1, "bend": 2
}

def create_stage_directories(stage_name):
    stage_dir = os.path.join(DATASETS_DIR, f"dataset_{stage_name}")
    img_train = os.path.join(stage_dir, "images", "train")
    img_val = os.path.join(stage_dir, "images", "val")
    txt_train = os.path.join(stage_dir, "labels", "train")
    txt_val = os.path.join(stage_dir, "labels", "val")

    # 기존 폴더 초기화 (잔재 파일 제거)
    if os.path.exists(stage_dir):
        shutil.rmtree(stage_dir)

    for path in [img_train, img_val, txt_train, txt_val]:
        os.makedirs(path, exist_ok=True)

    return stage_dir, img_train, img_val, txt_train, txt_val

def convert_labelme_json(json_path, img_w, img_h, class_mapping):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    yolo_lines = []
    for shape in data.get('shapes', []):
        label = shape.get('label')
        if label not in class_mapping:
            continue

        class_id = class_mapping[label]
        points = shape.get('points', [])

        if len(points) < 3:
            continue

        normalized_points = []
        for p in points:
            norm_x = min(max(p[0] / img_w, 0.0), 1.0)
            norm_y = min(max(p[1] / img_h, 0.0), 1.0)
            normalized_points.append(f"{norm_x:.6f} {norm_y:.6f}")

        points_str = " ".join(normalized_points)
        yolo_lines.append(f"{class_id} {points_str}")

    return yolo_lines

def create_yaml_file(stage_dir, stage_type, class_mapping):
    names_dict_lines = [
        f"  {cls_id}: '{name}'"
        for name, cls_id in sorted(class_mapping.items(), key=lambda x: x[1])
    ]
    names_str = "\n".join(names_dict_lines)

    yaml_content = f"""path: {stage_dir}
train: images/train
val: images/val

names:
{names_str}
"""
    yaml_path = os.path.join(DATASETS_DIR, f"data_{stage_type}.yaml")
    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write(yaml_content)
    print(f"📄 [{stage_type.upper()}] yaml 생성 완료: {yaml_path}")

def split_files_by_keyword(json_files, val_ratio=0.2):
    """ 파일명의 양품/불량 키워드를 기반으로 Train/Val 분할 """
    normal_files = []
    defect_files = []

    for f in json_files:
        filename = os.path.basename(f).lower()
        if 'normal' in filename:
            normal_files.append(f)
        else:
            defect_files.append(f)

    random.seed(42)
    random.shuffle(normal_files)
    random.shuffle(defect_files)

    # 각각 8:2 비율로 분할
    norm_val_cnt = max(1, int(len(normal_files) * val_ratio)) if normal_files else 0
    def_val_cnt = max(1, int(len(defect_files) * val_ratio)) if defect_files else 0

    val_files = set(normal_files[:norm_val_cnt] + defect_files[:def_val_cnt])

    print(f"📊 [데이터 분할 결과]")
    print(f"  - 정상(normal) 파일: 총 {len(normal_files)}개 (Train: {len(normal_files)-norm_val_cnt}, Val: {norm_val_cnt})")
    print(f"  - 불량 파일: 총 {len(defect_files)}개 (Train: {len(defect_files)-def_val_cnt}, Val: {def_val_cnt})")

    return val_files

def process_2stage_dataset(val_ratio=0.2):
    json_files = glob.glob(os.path.join(JSON_RAW_DIR, "*.json"))
    if not json_files:
        print(f"❌ 오류: '{JSON_RAW_DIR}' 디렉토리에서 .json 파일을 찾지 못했습니다!")
        return

    val_files = split_files_by_keyword(json_files, val_ratio)

    part_dir, p_img_train, p_img_val, p_txt_train, p_txt_val = create_stage_directories("part")
    defect_dir, d_img_train, d_img_val, d_txt_train, d_txt_val = create_stage_directories("defect")

    print(f"\n🚀 [환경: {'COLAB' if IS_COLAB else 'LOCAL'}] 변환 작업 시작...\n")

    part_count_total, defect_count_total = 0, 0

    for json_file in json_files:
        base_name = os.path.splitext(os.path.basename(json_file))[0]

        img_file = None
        for ext in ['.jpg', '.jpeg', '.png', '.JPG', '.PNG', '.JPEG']:
            possible_path = os.path.join(JSON_RAW_DIR, base_name + ext)
            if os.path.exists(possible_path):
                img_file = possible_path
                break

        if not img_file:
            continue

        try:
            with Image.open(img_file) as img:
                img_w, img_h = img.size
        except Exception as e:
            print(f"⚠️ 경고: {img_file} 읽기 실패 - {e}")
            continue

        part_yolo_lines = convert_labelme_json(json_file, img_w, img_h, PART_CLASS_MAPPING)
        defect_yolo_lines = convert_labelme_json(json_file, img_w, img_h, DEFECT_CLASS_MAPPING)

        is_val = json_file in val_files

        # 1. Part Dataset 저장 (모든 이미지 포함)
        target_p_img = p_img_val if is_val else p_img_train
        target_p_txt = p_txt_val if is_val else p_txt_train
        shutil.copy(img_file, os.path.join(target_p_img, os.path.basename(img_file)))
        with open(os.path.join(target_p_txt, base_name + ".txt"), 'w', encoding='utf-8') as f:
            f.write("\n".join(part_yolo_lines))
        part_count_total += len(part_yolo_lines)

        # 2. Defect Dataset 저장 (양품은 빈 txt로 저장되어 오탐 방지용 네거티브 샘플로 학습)
        target_d_img = d_img_val if is_val else d_img_train
        target_d_txt = d_txt_val if is_val else d_txt_train
        shutil.copy(img_file, os.path.join(target_d_img, os.path.basename(img_file)))
        with open(os.path.join(target_d_txt, base_name + ".txt"), 'w', encoding='utf-8') as f:
            f.write("\n".join(defect_yolo_lines))
        defect_count_total += len(defect_yolo_lines)

    create_yaml_file(part_dir, "part", PART_CLASS_MAPPING)
    create_yaml_file(defect_dir, "defect", DEFECT_CLASS_MAPPING)

    print("\n🎉 2-Stage 데이터 변환 완료!")
    print(f"  - [Part]   총 라벨 객체 수: {part_count_total}개")
    print(f"  - [Defect] 총 라벨 객체 수: {defect_count_total}개")

if __name__ == "__main__":
    process_2stage_dataset(val_ratio=0.2)