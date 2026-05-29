import json
import os
import random
import secrets
import shutil
import glob
from src.backend.celery_app import celery_app
from src.backend.redis_client import redis_conn

from src.generator.audio_mixer import AudioMixer
from src.generator.image_composer import ImageComposer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
RAW_AUDIO_DIR = os.path.join(PROJECT_ROOT, "dataset", "raw_assets", "audio")
RAW_IMAGE_DIR = os.path.join(PROJECT_ROOT, "dataset", "raw_assets", "images")
RUNTIME_DIR = os.path.join(PROJECT_ROOT, "dataset", "runtime_challenges")

rng = random.SystemRandom()

def _safe_remove_tree(path):
    if not path:
        return
    root = os.path.abspath(RUNTIME_DIR)
    target = os.path.abspath(path)
    if os.path.commonpath([root, target]) != root:
        return
    shutil.rmtree(target, ignore_errors=True)

def _get_matched_assets():
    audio_files = []
    for ext in ("*.wav", "*.mp3", "*.ogg", "*.flac"):
        audio_files.extend(glob.glob(os.path.join(RAW_AUDIO_DIR, ext)))

    categories = []
    for audio_path in audio_files:
        label = os.path.splitext(os.path.basename(audio_path))[0].lower()
        image_dir = os.path.join(RAW_IMAGE_DIR, label)
        images = []
        if os.path.isdir(image_dir):
            for ext in ("*.png", "*.jpg", "*.jpeg"):
                images.extend(glob.glob(os.path.join(image_dir, ext)))
        if images:
            categories.append({"label": label, "audio": audio_path, "images": images})

    # Dataset Virtual Augmentation | 数据集虚拟增强
    # To ensure high variety of generated captchas despite a limited local dataset, | 为了在有限的本地数据集下保证生成验证码的高多样性，
    # we virtually expand the pool. The downstream audio_mixer and image_composer | 我们虚拟地扩展了数据池。下游的 audio_mixer 和 image_composer
    # will apply heavy randomized augmentations (pitch, speed, affine transforms) | 将应用重度随机增强（音高、速度、仿射变换）
    # ensuring that these virtual duplicates produce unique CAPTCHA challenges. | 确保这些虚拟副本产生独一无二的验证码挑战。
    MIN_POOL_SIZE = 200
    if categories and len(categories) < MIN_POOL_SIZE:
        base_categories = list(categories)
        while len(categories) < MIN_POOL_SIZE:
            categories.extend(base_categories)
        categories = categories[:MIN_POOL_SIZE]

    return categories

def _audio_start_times(count, difficulty):
    start_times = []
    current = rng.uniform(0.35, 0.7)
    for _ in range(count):
        start_times.append(round(current, 2))
        current += rng.uniform(1.05, 1.75 if difficulty < 3 else 1.45)
    return start_times

@celery_app.task(name="tasks.generate_captcha")
def generate_captcha(difficulty=1):
    challenge_id = secrets.token_urlsafe(32)
    categories = _get_matched_assets()
    if len(categories) < 3:
        raise ValueError("Matched categories less than 3")

    question_type = rng.choice(["temporal", "exclusion"])
    if question_type == "temporal":
        num_items = rng.randint(3 if difficulty >= 2 else 2, min(4, len(categories)))
        selected_cats = rng.sample(categories, num_items)
        selected_audios = [cat["audio"] for cat in selected_cats]
        selected_images = [rng.choice(cat["images"]) for cat in selected_cats]
        start_times = _audio_start_times(num_items, difficulty)
        target_index = rng.randint(0, num_items - 1)
        target_label = selected_cats[target_index]["label"]
        question_text = f"Please click the object corresponding to sound #{target_index + 1}"
    else:
        num_items = 3
        selected_cats = rng.sample(categories, num_items)
        selected_images = [rng.choice(cat["images"]) for cat in selected_cats]
        sound_indices = rng.sample(range(num_items), 2)
        silent_index = [idx for idx in range(num_items) if idx not in sound_indices][0]
        selected_audios = [selected_cats[idx]["audio"] for idx in sound_indices]
        first_start = rng.uniform(0.35, 0.65)
        start_times = [round(first_start, 2), round(first_start + rng.uniform(0.08, 0.34), 2)]
        target_label = selected_cats[silent_index]["label"]
        question_text = "Please click the object that did NOT make a sound"

    rng.shuffle(selected_images)
    asset_dir = os.path.join(RUNTIME_DIR, challenge_id)
    os.makedirs(asset_dir, exist_ok=True)

    try:
        mixer = AudioMixer()
        composer = ImageComposer(canvas_size=(600, 300))
        audio_meta = mixer.create_sequence(None, selected_audios, start_times, os.path.join(asset_dir, "mixed.wav"))
        image_meta = composer.generate_captcha_image(selected_images, os.path.join(asset_dir, "captcha.png"))

        target_bbox = None
        for item in image_meta:
            if item.get("label") == target_label:
                target_bbox = item["bbox"]
                break

        if not target_bbox:
            raise ValueError("Generated challenge has no target")
            
        challenge_data = {
            "challenge_id": challenge_id,
            "asset_dir": asset_dir,
            "difficulty": difficulty,
            "answer": {
                "question_type": question_type,
                "question_text": question_text,
                "audio_metadata": audio_meta,
                "image_metadata": image_meta,
                "target": {"label": target_label, "bbox": target_bbox},
                "audio_answer": target_label,
            }
        }
        
        # Push to Redis pool | 推送到 Redis 缓冲池
        redis_conn.lpush(f"captcha_pool:{difficulty}", json.dumps(challenge_data))
        
    except Exception as e:
        _safe_remove_tree(asset_dir)
        raise e
