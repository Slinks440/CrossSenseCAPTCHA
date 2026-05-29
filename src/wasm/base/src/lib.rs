use wasm_bindgen::prelude::*;
use x25519_dalek::{PublicKey, StaticSecret};
use aes_gcm::{
    aead::{Aead, KeyInit},
    Aes256Gcm, Nonce,
};
use hkdf::Hkdf;
use sha2::Sha256;
use rand_core::OsRng;
use serde::{Deserialize, Serialize};
use base64::{engine::general_purpose::STANDARD as BASE64, Engine};

#[wasm_bindgen(start)]
pub fn main() {
    console_error_panic_hook::set_once();
}

#[derive(Deserialize, Serialize)]
struct EncryptWrapper {
    client_pub: String,
    ciphertext: String,
}

#[derive(Serialize)]
struct IntermPayload {
    logic_data: serde_json::Value,
    lsh: String,
    client_sign_nonce: String,
    is_touch: bool,
}

#[wasm_bindgen]
pub fn encrypt_payload(
    logic_data_bytes: &mut [u8], 
    server_pub_key_b64: &str, 
    server_nonce_b64: &str, 
    js_entropy: &str, 
    lsh: &str, 
    is_touch: bool
) -> Result<String, JsValue> {
    
    let logic_data: serde_json::Value = serde_json::from_slice(logic_data_bytes)
        .map_err(|_| JsValue::from_str("Invalid logic data"))?;
        
    // Zero-fill the rust-side slice immediately
    logic_data_bytes.fill(0);
    
    // 1. Decode Server Materials
    let server_pub_bytes = BASE64.decode(server_pub_key_b64).map_err(|_| JsValue::from_str("Invalid server pub key"))?;
    let server_nonce_bytes = BASE64.decode(server_nonce_b64).map_err(|_| JsValue::from_str("Invalid server nonce"))?;
    
    let mut pub_key_arr = [0u8; 32];
    pub_key_arr.copy_from_slice(&server_pub_bytes[0..32]);
    let server_pub = PublicKey::from(pub_key_arr);
    
    // 2. Generate Client Keypair
    let client_secret = StaticSecret::random_from_rng(OsRng);
    let client_pub = PublicKey::from(&client_secret);
    let shared_secret = client_secret.diffie_hellman(&server_pub);
    
    // 3. HKDF
    let hkdf = Hkdf::<Sha256>::new(Some(&server_nonce_bytes), shared_secret.as_bytes());
    let mut okm = [0u8; 32 + 12 + 32];
    hkdf.expand(js_entropy.as_bytes(), &mut okm).map_err(|_| JsValue::from_str("HKDF failed"))?;
    
    let aes_key = &okm[0..32];
    let aes_iv = &okm[32..44];
    let client_sign_nonce = BASE64.encode(&okm[44..76]);
    
    let full_payload = IntermPayload {
        logic_data,
        lsh: lsh.to_string(),
        client_sign_nonce,
        is_touch,
    };
    
    // Secure clear of intermediate buffer
    let mut payload_json = serde_json::to_vec(&full_payload).unwrap();
    
    // 4. AES-256-GCM
    let cipher = Aes256Gcm::new(aes_key.into());
    let nonce = Nonce::from_slice(aes_iv);
    
    let ciphertext = cipher.encrypt(nonce, payload_json.as_ref())
        .map_err(|_| JsValue::from_str("Encryption failed"))?;
        
    payload_json.fill(0); // Zero fill memory
    
    let wrapper = EncryptWrapper {
        client_pub: BASE64.encode(client_pub.as_bytes()),
        ciphertext: BASE64.encode(ciphertext),
    };
    
    Ok(serde_json::to_string(&wrapper).unwrap())
}
