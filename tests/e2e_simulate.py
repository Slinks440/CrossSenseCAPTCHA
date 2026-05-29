import requests
import json
import base64
import hashlib
import time
import hmac
import struct
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

BASE_URL = "http://127.0.0.1:5000"

def simulate_pow(init_seed, difficulty):
    # Dummy PoW simulation for E2E testing
    # In real scenario, it would run the pointer chasing algorithm
    # Here we just bypass or send a dummy if validator is mocked
    return "dummy_pow_hash"

def run_e2e():
    session = requests.Session()
    
    # 1. Init
    print("[*] Calling /api/init")
    resp = session.get(f"{BASE_URL}/api/init")
    if resp.status_code != 200:
        print("Failed to init:", resp.text)
        return False
    data = resp.json()
    init_seed = data["init_seed"]
    difficulty = data["difficulty"]
    
    # 2. Captcha
    print("[*] Calling /api/captcha")
    pow_result = simulate_pow(init_seed, difficulty)
    resp = session.post(f"{BASE_URL}/api/captcha", json={"pow_result": pow_result})
    if resp.status_code != 200:
        print("Failed to get captcha:", resp.text)
        return False
    data = resp.json()
    challenge_id = data["challenge_id"]
    server_pub_b64 = data["server_pub_key"]
    server_nonce_b64 = data["server_nonce"]
    
    # 3. Cryptography & Logic Build
    print("[*] Generating Payload")
    server_pub_bytes = base64.b64decode(server_pub_b64)
    server_nonce_bytes = base64.b64decode(server_nonce_b64)
    server_pub = x25519.X25519PublicKey.from_public_bytes(server_pub_bytes)
    
    client_priv = x25519.X25519PrivateKey.generate()
    client_pub = client_priv.public_key()
    client_pub_bytes = client_pub.public_bytes(encoding=None, format=None) # needs proper serialization in real usage
    # Actually using proper serialization:
    from cryptography.hazmat.primitives import serialization
    client_pub_bytes = client_pub.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    client_pub_b64 = base64.b64encode(client_pub_bytes).decode('utf-8')
    
    shared_secret = client_priv.exchange(server_pub)
    
    js_entropy = "dummy_entropy_123"
    hkdf = HKDF(algorithm=hashes.SHA256(), length=76, salt=server_nonce_bytes, info=js_entropy.encode('utf-8'))
    okm = hkdf.derive(shared_secret)
    aes_key = okm[0:32]
    aes_iv = okm[32:44]
    
    # Events dummy
    events = [{"x": 10, "y": 10, "dt": 16, "force": 0, "radius": 0}]
    computed_mac = hmac.new(aes_key, digestmod=hashlib.sha256)
    for e in events:
        computed_mac.update(struct.pack('<h', e["x"]))
        computed_mac.update(struct.pack('<h', e["y"]))
        computed_mac.update(struct.pack('<H', e["dt"]))
        computed_mac.update(struct.pack('<B', e["force"]))
        computed_mac.update(struct.pack('<B', e["radius"]))
        
    logic_data = {
        "events": events,
        "delta_react": 100,
        "event_mac": computed_mac.hexdigest()
    }
    
    payload = {
        "logic_data": logic_data,
        "is_touch": False,
        "lsh": "dummy_lsh"
    }
    
    aesgcm = AESGCM(aes_key)
    ciphertext = aesgcm.encrypt(aes_iv, json.dumps(payload).encode('utf-8'), None)
    ciphertext_b64 = base64.b64encode(ciphertext).decode('utf-8')
    
    # 4. Verify
    print("[*] Calling /api/verify")
    resp = session.post(f"{BASE_URL}/api/verify", json={
        "challenge_id": challenge_id,
        "js_entropy": js_entropy,
        "client_pub": client_pub_b64,
        "ciphertext": ciphertext_b64
    })
    
    if resp.status_code == 200:
        print("Success:", resp.json())
        return True
    else:
        print("Failed:", resp.text)
        return False

if __name__ == "__main__":
    run_e2e()
