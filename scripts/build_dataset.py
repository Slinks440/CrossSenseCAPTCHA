import os
import sys
import random
import json
import glob

# Dynamically import src / 动态引入 src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.generator.audio_mixer import AudioMixer
from src.generator.image_composer import ImageComposer

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RAW_AUDIO_DIR = os.path.join(BASE_DIR, "dataset", "raw_assets", "audio")
RAW_IMAGE_DIR = os.path.join(BASE_DIR, "dataset", "raw_assets", "images")
OUTPUT_DIR = os.path.join(BASE_DIR, "dataset", "generated_samples")

def get_matched_assets():
    """
    Match multimodal assets / 匹配多模态资产
    """
    audio_files = []
    for ext in ('*.wav', '*.mp3', '*.ogg', '*.flac'):
        audio_files.extend(glob.glob(os.path.join(RAW_AUDIO_DIR, ext)))

    categories = []
    for audio_path in audio_files:
        base_name = os.path.splitext(os.path.basename(audio_path))[0].lower()
        folder_path = os.path.join(RAW_IMAGE_DIR, base_name)
        
        image_list = []
        if os.path.isdir(folder_path):
            for ext in ('*.png', '*.jpg', '*.jpeg'):
                image_list.extend(glob.glob(os.path.join(folder_path, ext)))

        if image_list:
            categories.append({
                "label": base_name,
                "audio": audio_path,
                "images": image_list
            })
        else:
            print(f"Skipped missing image resources / 略过缺失图片资源: {base_name}")

    return categories

def build():
    categories = get_matched_assets()
    rng = random.SystemRandom()
    
    if len(categories) < 3:
        print("Error: Matched categories less than 3 / 匹配分类少于3个。")
        return

    mixer = AudioMixer()
    composer = ImageComposer(canvas_size=(600, 300))
    
    # Generate 20 samples to see a good mix of both types
    # 生成 20 道题目以展示两种题型的混合效果
    num_samples = int(os.environ.get("NUM_SAMPLES", "60"))
    print(f"Matched {len(categories)} categories. Generating {num_samples} samples... / 开始生成样本...")
    
    for i in range(num_samples):
        sample_dir = os.path.join(OUTPUT_DIR, f"sample_{i:03d}")
        os.makedirs(sample_dir, exist_ok=True)
        
        # Randomly choose question type / 随机选择题型
        question_type = rng.choice(["temporal", "exclusion"])
        
        if question_type == "temporal":
            # --- Type A: Temporal Matching / 传统时序题 ---
            num_items = rng.randint(2, min(4, len(categories)))
            selected_cats = rng.sample(categories, num_items)
            
            selected_audios = [cat["audio"] for cat in selected_cats]
            selected_images = [rng.choice(cat["images"]) for cat in selected_cats]
            
            # Sequenced audio / 按时序发声
            start_times = []
            current_time = rng.uniform(0.35, 0.75)
            for _ in range(num_items):
                start_times.append(round(current_time, 2))
                current_time += rng.uniform(1.15, 1.85)
            
            target_index = rng.randint(0, num_items - 1)
            target_label = selected_cats[target_index]["label"]
            question_text = f"Please click the object corresponding to sound #{target_index + 1} / 请点击第 {target_index + 1} 个发出声音的物体"
            
        else:
            # --- Type B: Exclusion Strategy / 叠加排除题 (Your New Logic) ---
            num_items = 3
            selected_cats = rng.sample(categories, num_items)
            selected_images = [rng.choice(cat["images"]) for cat in selected_cats]
            
            # Pick 2 to make sound, 1 to be silent / 选2个发声，1个静音
            sound_indices = rng.sample(range(num_items), 2)
            silent_index = [x for x in range(num_items) if x not in sound_indices][0]
            
            selected_audios = [selected_cats[idx]["audio"] for idx in sound_indices]
            
            # Overlap audio with a tiny offset (0.1s) for realism / 重叠播放，带0.1秒微小延迟增加真实感
            first_start = rng.uniform(0.35, 0.65)
            start_times = [round(first_start, 2), round(first_start + rng.uniform(0.08, 0.34), 2)]
            
            target_label = selected_cats[silent_index]["label"]
            question_text = "Please click the object that did NOT make a sound / 请点击未发出声音的物体"


        # Common generation steps / 通用的音频、图像合成与保存逻辑
        rng.shuffle(selected_images)

        out_audio = os.path.join(sample_dir, "mixed.wav")
        audio_meta = mixer.create_sequence(None, selected_audios, start_times, out_audio)
        
        out_image = os.path.join(sample_dir, "captcha.png")
        image_meta = composer.generate_captcha_image(selected_images, out_image)
        
        target_bbox = None
        for item in image_meta:
            if item.get("label") == target_label:
                target_bbox = item["bbox"]
                break
                
        answer_data = {
            "question_type": question_type,
            "question_text": question_text,
            "audio_metadata": audio_meta,
            "image_metadata": image_meta,
            "target": {
                "label": target_label,
                "bbox": target_bbox
            }
        }
        
        with open(os.path.join(sample_dir, "answer.json"), "w", encoding="utf-8") as f:
            json.dump(answer_data, f, indent=4, ensure_ascii=False)
            
        print(f"Generated sample_{i:03d} [{question_type.upper()}] (Target: {target_label})")

if __name__ == "__main__":
    build()
