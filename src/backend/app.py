import json
import os
import secrets
import shutil
import sys
import time
import base64
import jwt
import hashlib
import logging

import asyncio
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, abort, jsonify, make_response, request, send_file
from werkzeug.middleware.proxy_fix import ProxyFix

pow_executor = ThreadPoolExecutor(max_workers=8)
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# V13: Telemetry Pipeline | 遥测流水线
try:
    from confluent_kafka import Producer
    kafka_producer = Producer({'bootstrap.servers': os.environ.get('KAFKA_BROKER', 'localhost:9092')})
except ImportError:
    kafka_producer = None
    logging.warning("confluent_kafka not installed. Telemetry offline.")

# V12: Rust PyO3 PoW Validator | Rust PyO3 PoW 验证器
try:
    import pow_ext
except ImportError:
    pow_ext = None
    logging.warning("pow_ext not installed. Using unsafe fallback.")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.backend.detector import AttackerDetector
from src.backend.validator import AnswerValidator
from src.backend.redis_client import redis_conn, getdel_script, RedisLock, token_bucket_script
from src.backend.tasks import generate_captcha
from src.backend.tasks import generate_captcha

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
jwt_secret = os.environ.get("JWT_SECRET")
if not jwt_secret:
    raise RuntimeError("CRITICAL SECURITY ERROR: JWT_SECRET environment variable is not set.")
app.config["JWT_SECRET"] = jwt_secret

if os.environ.get("USE_PROXY"):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
RUNTIME_DIR = os.path.join(PROJECT_ROOT, "dataset", "runtime_challenges")

validator = AnswerValidator(tolerance=6)
detector = AttackerDetector()

ALLOWED_ASSETS = {"captcha.png", "mixed.wav"}
SESSION_COOKIE = "csc_session"
SESSION_MAX_AGE_SECONDS = 3600
CHALLENGE_TTL_SECONDS = 120

def _clear_runtime_dir_on_startup():
    root = os.path.abspath(RUNTIME_DIR)
    os.makedirs(root, exist_ok=True)
    try:
        for name in os.listdir(root):
            path = os.path.abspath(os.path.join(root, name))
            if os.path.commonpath([root, path]) != root: continue
            if os.path.isdir(path): shutil.rmtree(path, ignore_errors=True)
            else:
                try: os.remove(path)
                except OSError: pass
    except OSError:
        pass

_clear_runtime_dir_on_startup()

def _check_legacy_rate_limit(ip):
    # DEPRECATED: Rate limiting moved to Nginx/Gateway to prevent application layer DDoS | 已废弃：限流已移至 Nginx/网关以防止应用层 DDoS
    return True

def send_telemetry(event_type, payload):
    if kafka_producer:
        try:
            kafka_producer.produce('captcha_telemetry', key=event_type, value=json.dumps(payload))
            kafka_producer.poll(0)
        except Exception:
            pass

@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response

def _now():
    return time.time()

def _get_or_create_session_id():
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id and 24 <= len(session_id) <= 128 and all(ch.isalnum() or ch in "-_" for ch in session_id):
        return session_id, False
    return secrets.token_urlsafe(32), True

def _get_existing_session_id():
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id or not (24 <= len(session_id) <= 128) or not all(ch.isalnum() or ch in "-_" for ch in session_id):
        return None
    return session_id

def _public_client_fingerprint(session_id=None):
    # Removed session_id to prevent Sybil Session Bypass | 移除 session_id 以防止女巫会话绕过
    user_agent = request.headers.get("User-Agent", "")
    accept_language = request.headers.get("Accept-Language", "")
    ip_subnet = '.'.join((request.remote_addr or "127.0.0.1").split('.')[:3])
    return hashlib.sha256(f"{user_agent[:160]}|{accept_language[:80]}|{ip_subnet}".encode("utf-8")).hexdigest()

def _client_key(session_id):
    return hashlib.sha256(f"{_public_client_fingerprint(session_id)}|{session_id}".encode("utf-8")).hexdigest()

def _client_difficulty(client_key):
    diff = redis_conn.get(f"client:{client_key}:difficulty")
    return int(diff) if diff else 1

def _json_failure(message, status=200):
    return jsonify({"success": False, "msg": message}), status

@app.route("/")
def index():
    html_path = os.path.join(BASE_DIR, "frontend", "index.html")
    return send_file(html_path)

@app.route("/pkg/<path:filename>")
def serve_pkg(filename):
    # Support multiple wasm bundles in V12 | 在 V12 中支持多个 wasm 包
    base_pkg_dir = os.path.join(BASE_DIR, "wasm", "base", "pkg")
    logic_pkg_dir = os.path.join(BASE_DIR, "wasm", "logic", "pkg")
    
    # Try logic first, then base | 先尝试 logic 包，再尝试 base 包
    file_path = os.path.abspath(os.path.join(logic_pkg_dir, filename))
    if not os.path.isfile(file_path):
        file_path = os.path.abspath(os.path.join(base_pkg_dir, filename))
        if not os.path.isfile(file_path):
            abort(404)
            
    response = make_response(send_file(file_path))
    if filename.endswith('.wasm'):
        response.headers['Content-Type'] = 'application/wasm'
    return response

@app.route("/assets/<challenge_id>/<filename>")
def serve_asset(challenge_id, filename):
    if filename not in ALLOWED_ASSETS: abort(404)
    if not _get_existing_session_id(): abort(404)
    challenge_str = redis_conn.get(f"challenge:{challenge_id}")
    if not challenge_str: abort(404)
    asset_dir = json.loads(challenge_str)["asset_dir"]
    file_path = os.path.abspath(os.path.join(asset_dir, filename))
    if os.path.commonpath([os.path.abspath(asset_dir), file_path]) != os.path.abspath(asset_dir) or not os.path.isfile(file_path):
        abort(404)
    response = make_response(send_file(file_path, max_age=0))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

@app.route("/api/init", methods=["GET"])
def init_captcha():
    session_id, is_new_session = _get_or_create_session_id()
    client_key = _client_key(session_id)
    client_fp = _public_client_fingerprint(session_id)
    
    init_seed = secrets.token_hex(32)
    difficulty = _client_difficulty(client_fp)
    
    redis_conn.set(f"pow:{client_key}", init_seed, ex=300)
    
    response = jsonify({"init_seed": init_seed, "difficulty": difficulty})
    if is_new_session:
        response.set_cookie(SESSION_COOKIE, session_id, max_age=SESSION_MAX_AGE_SECONDS, httponly=True, secure=request.is_secure, samesite="Strict")
    return response

@app.route("/api/captcha", methods=["POST"])
async def get_captcha():
    session_id = _get_existing_session_id()
    if not session_id: return _json_failure("Session invalid", 403)
    client_key = _client_key(session_id)

    data = request.get_json(silent=True) or {}
    pow_result = data.get("pow_result")
    
    expected_seed = redis_conn.get(f"pow:{client_key}")
    if not expected_seed or not pow_result:
        return _json_failure("PoW missing or expired", 403)
        
    # V12: Real PoW Check via PyO3 Extension | 通过 PyO3 扩展进行真正的 PoW 校验
    client_fp = _public_client_fingerprint(session_id)
    difficulty = _client_difficulty(client_fp)
    if pow_ext:
        try:
            loop = asyncio.get_running_loop()
            expected_hash = await loop.run_in_executor(pow_executor, pow_ext.validate_pow, expected_seed, difficulty)
            if pow_result != expected_hash:
                send_telemetry("pow_failure", {"ip": request.remote_addr, "client_fp": client_fp, "expected": expected_hash, "got": pow_result})
                return _json_failure("PoW hash mismatch", 403)
        except Exception as e:
            return _json_failure("PoW computation error", 500)
    
    redis_conn.delete(f"pow:{client_key}")
    
    pool_key = f"captcha_pool:{difficulty}"
    if redis_conn.llen(pool_key) < 10:
        lock = RedisLock(f"lock:gen_pool:{difficulty}", "1", timeout=2)
        if lock.acquire():
            try:
                shortfall = 10 - redis_conn.llen(pool_key)
                for _ in range(min(shortfall, 5)):
                    generate_captcha.delay(difficulty=difficulty)
            finally:
                lock.release()
            
    challenge_data_str = redis_conn.brpop(pool_key, timeout=3)
    if not challenge_data_str: return jsonify({"error": "Service busy"}), 503
        
    challenge_data = json.loads(challenge_data_str[1])
    challenge_id = challenge_data["challenge_id"]
    
    challenge = {
        "answer": challenge_data["answer"],
        "asset_dir": challenge_data["asset_dir"],
        "client_key": client_key,
        "difficulty": difficulty,
    }
    redis_conn.set(f"challenge:{challenge_id}", json.dumps(challenge), ex=CHALLENGE_TTL_SECONDS)

    server_private_key = x25519.X25519PrivateKey.generate()
    server_public_key = server_private_key.public_key()
    
    priv_bytes = server_private_key.private_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw, encryption_algorithm=serialization.NoEncryption()
    )
    pub_bytes = server_public_key.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    
    server_nonce = secrets.token_bytes(32)

    # V14 Fix: Dynamic Target Obfuscation using server_nonce instead of client seed | 修复：使用 server_nonce 而不是客户端种子进行动态目标混淆
    bbox = challenge_data["answer"].get("target", {}).get("bbox", [0,0,0,0])
    target_x = (bbox[0] + bbox[2]) / 2.0
    target_y = (bbox[1] + bbox[3]) / 2.0
    
    import struct
    obs_key = int.from_bytes(server_nonce[:4], byteorder='little')
    obs_x = struct.unpack('<I', struct.pack('<f', target_x))[0] ^ obs_key
    obs_y = struct.unpack('<I', struct.pack('<f', target_y))[0] ^ obs_key

    redis_conn.set(f"crypto:{challenge_id}", base64.b64encode(priv_bytes).decode('utf-8'), ex=CHALLENGE_TTL_SECONDS)
    redis_conn.set(f"nonce:{challenge_id}", base64.b64encode(server_nonce).decode('utf-8'), ex=CHALLENGE_TTL_SECONDS)

    send_telemetry("challenge_issued", {"ip": request.remote_addr, "client_fp": client_fp, "difficulty": difficulty})

    return jsonify({
        "challenge_id": challenge_id,
        "image_url": f"/assets/{challenge_id}/captcha.png",
        "audio_url": f"/assets/{challenge_id}/mixed.wav",
        "question_text": challenge_data["answer"].get("question_text", "Please select the target"),
        "server_pub_key": base64.b64encode(pub_bytes).decode('utf-8'),
        "server_nonce": base64.b64encode(server_nonce).decode('utf-8'),
        "obs_x": obs_x,
        "obs_y": obs_y,
        "seed_num": obs_key
    })

@app.route("/api/verify", methods=["POST"])
def verify_captcha():
    session_id = _get_existing_session_id()
    if not session_id: return _json_failure("Verification failed")
    client_key = _client_key(session_id)

    data = request.get_json(silent=True) or {}
    challenge_id = data.get("challenge_id")
    js_entropy = data.get("js_entropy", "")
    client_pub_b64 = data.get("client_pub")
    ciphertext_b64 = data.get("ciphertext")

    if not challenge_id or not client_pub_b64 or not ciphertext_b64:
        return _json_failure("Verification failed")

    priv_b64 = getdel_script(keys=[f"crypto:{challenge_id}"])
    if not priv_b64: return _json_failure("Verification failed - Replay Detected")
    server_nonce_b64 = getdel_script(keys=[f"nonce:{challenge_id}"])
    
    challenge_str = getdel_script(keys=[f"challenge:{challenge_id}"])
    if not challenge_str: return _json_failure("Verification failed")
    challenge = json.loads(challenge_str)
    
    if challenge["client_key"] != client_key: return _json_failure("Verification failed")

    try:
        server_priv_bytes = base64.b64decode(priv_b64)
        server_nonce_bytes = base64.b64decode(server_nonce_b64)
        client_pub_bytes = base64.b64decode(client_pub_b64)
        
        server_priv_key = x25519.X25519PrivateKey.from_private_bytes(server_priv_bytes)
        client_pub_key = x25519.X25519PublicKey.from_public_bytes(client_pub_bytes)
        
        shared_secret = server_priv_key.exchange(client_pub_key)
        
        hkdf = HKDF(algorithm=hashes.SHA256(), length=76, salt=server_nonce_bytes, info=js_entropy.encode('utf-8'))
        okm = hkdf.derive(shared_secret)
        aes_key = okm[0:32]
        aes_iv = okm[32:44]
        client_sign_nonce = base64.b64encode(okm[44:76]).decode('utf-8')
        
        aesgcm = AESGCM(aes_key)
        plaintext = aesgcm.decrypt(aes_iv, base64.b64decode(ciphertext_b64), None)
        wasm_payload = json.loads(plaintext)
    except Exception as e:
        return _json_failure(f"Crypto validation failed")

    logic_data = wasm_payload.get("logic_data", {})
    is_touch = wasm_payload.get("is_touch", False)
    lsh = wasm_payload.get("lsh", "")

    # V14 HMAC Verification Implementation | HMAC 验证实现
    event_mac = logic_data.get("event_mac", "")
    events = logic_data.get("events", [])
    
    import struct
    import hmac
    
    computed_mac = hmac.new(aes_key, digestmod=hashlib.sha256)
    try:
        for e in events:
            computed_mac.update(struct.pack('<h', e.get("x", 0)))  # i16 is 'h'
            computed_mac.update(struct.pack('<h', e.get("y", 0)))
            computed_mac.update(struct.pack('<H', e.get("dt", 0))) # u16 is 'H'
            computed_mac.update(struct.pack('<B', e.get("force", 0)))
            computed_mac.update(struct.pack('<B', e.get("radius", 0)))
    except struct.error:
        return _json_failure("Malformed payload", 400)
        
    if not hmac.compare_digest(computed_mac.hexdigest(), event_mac):
        return _json_failure("Memory tamper detected", 403)

    client_fp = _public_client_fingerprint(session_id)
    is_bot, risk, reason = detector.analyze_behavior(_now() * 1000, logic_data, is_touch=is_touch, difficulty=challenge["difficulty"])
    
    send_telemetry("verification_attempt", {
        "ip": request.remote_addr, 
        "client_fp": client_fp,
        "is_bot": is_bot, 
        "risk": risk, 
        "reason": reason, 
        "lsh": lsh,
        "delta": logic_data.get("delta_react")
    })

    if is_bot: return _json_failure("Verification failed")
        
    events = logic_data.get("events", [])
    if not events: return _json_failure("Verification failed")
        
    click_x, click_y = 0, 0
    for e in events:
        click_x += e.get("x", 0)
        click_y += e.get("y", 0)

    target_bbox = challenge["answer"].get("target", {}).get("bbox")
    if not target_bbox or not validator.check_click(target_bbox, click_x, click_y):
        return _json_failure("Verification failed")

    asset_dir = challenge.get("asset_dir")
    if asset_dir and os.path.exists(asset_dir): shutil.rmtree(asset_dir, ignore_errors=True)

    sign_seed = secrets.token_hex(16)
    token = jwt.encode({"client": client_key, "exp": _now() + 300, "sign_seed": sign_seed, "act": "verify_captcha", "aud": "frontend"}, app.config["JWT_SECRET"], algorithm="HS256")

    response = jsonify({"success": True, "msg": "Verification passed", "sign_seed": sign_seed})
    response.set_cookie("CaptchaToken", token, max_age=300, httponly=True, secure=request.is_secure, samesite="Strict")
    return response



if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=5000)
