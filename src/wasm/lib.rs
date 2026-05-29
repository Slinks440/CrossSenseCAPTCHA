use wasm_bindgen::prelude::*;
use std::cell::RefCell;
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
use hmac::{Hmac, Mac};

// Static Ring Buffer Configuration | 静态环形缓冲区配置
const MAX_EVENTS: usize = 1024;
const FRICTION_TARGET_X: f32 = 150.0; // In production, these should be dynamically securely injected | 在生产环境中，这些应该动态安全注入
const FRICTION_TARGET_Y: f32 = 150.0;
const FRICTION_RADIUS: f32 = 50.0;

#[derive(Clone, Copy, Default, Debug, Serialize)]
struct TouchEvent {
    x: i16, // Differential coordinates
    y: i16,
    dt: u16, // Delta time
    force: u8,
    radius: u8,
}

struct RingBuffer {
    events: [TouchEvent; MAX_EVENTS],
    head: usize,
    count: usize,
    friction_triggered_at: Option<u32>, // Accumulated elapsed time when triggered
    total_time: u32,
    last_x: f32,
    last_y: f32,
}

impl RingBuffer {
    const fn new() -> Self {
        Self {
            events: [TouchEvent { x: 0, y: 0, dt: 0, force: 0, radius: 0 }; MAX_EVENTS],
            head: 0,
            count: 0,
            friction_triggered_at: None,
            total_time: 0,
            last_x: 0.0,
            last_y: 0.0,
        }
    }

    fn push(&mut self, x: f32, y: f32, dt: f32, force: f32, radius: f32) {
        let dt_u16 = dt.clamp(0.0, 65535.0) as u16;
        
        // Differential encoding for highly compact memory layout
        let dx = x - self.last_x;
        let dy = y - self.last_y;
        self.last_x = x;
        self.last_y = y;

        let event = TouchEvent {
            x: dx.clamp(-32768.0, 32767.0) as i16,
            y: dy.clamp(-32768.0, 32767.0) as i16,
            dt: dt_u16,
            force: (force * 255.0).clamp(0.0, 255.0) as u8,
            radius: radius.clamp(0.0, 255.0) as u8,
        };

        self.events[self.head] = event;
        self.head = (self.head + 1) % MAX_EVENTS;
        if self.count < MAX_EVENTS {
            self.count += 1;
        }
        self.total_time = self.total_time.saturating_add(dt_u16 as u32);
    }
    
    fn get_events(&self) -> Vec<TouchEvent> {
        let mut result = Vec::with_capacity(self.count);
        let start = if self.count < MAX_EVENTS { 0 } else { self.head };
        for i in 0..self.count {
            result.push(self.events[(start + i) % MAX_EVENTS]);
        }
        result
    }

    fn reset(&mut self) {
        self.head = 0;
        self.count = 0;
        self.friction_triggered_at = None;
        self.total_time = 0;
        self.last_x = 0.0;
        self.last_y = 0.0;
    }
}

// Strictly isolated thread_local memory pool, banning zero-copy memory exposure to JS | 严格隔离的 thread_local 内存池，禁止将零拷贝内存暴露给 JS
thread_local! {
    static BUFFER: RefCell<RingBuffer> = RefCell::new(RingBuffer::new());
}

#[wasm_bindgen]
pub fn push_event(x: f32, y: f32, dt: f32, force: f32, radius: f32) {
    BUFFER.with(|b| {
        b.borrow_mut().push(x, y, dt, force, radius);
    });
}

#[wasm_bindgen]
pub fn check_friction_trigger(x: f32, y: f32) -> f32 {
    let dx = x - FRICTION_TARGET_X;
    let dy = y - FRICTION_TARGET_Y;
    let dist = (dx * dx + dy * dy).sqrt();
    
    if dist < FRICTION_RADIUS {
        BUFFER.with(|b| {
            let mut buf = b.borrow_mut();
            if buf.friction_triggered_at.is_none() {
                buf.friction_triggered_at = Some(buf.total_time);
            }
        });
        return 1.8; // Return physical resistance coefficient
    }
    1.0
}

#[derive(Serialize)]
struct FinalPayload {
    events: Vec<TouchEvent>,
    delta_react: Option<i32>,
    lsh: String, // Hardware anchor (e.g. WebGL hash)
    client_sign_nonce: String,
    event_mac: String,
}

#[wasm_bindgen]
pub fn finalize_and_encrypt(server_pub_key_b64: &str, server_nonce_b64: &str, js_entropy: &str, lsh: &str) -> Result<String, JsValue> {
    let mut payload_obj = FinalPayload {
        events: Vec::new(),
        delta_react: None,
        lsh: lsh.to_string(),
        client_sign_nonce: String::new(),
        event_mac: String::new(),
    };

    BUFFER.with(|b| {
        let mut buf = b.borrow_mut();
        payload_obj.events = buf.get_events();
        
        // Calculate Biological Delta (Reaction Time: T_react - T_perturb) | 计算生物反应时间差 (反应时间: T_react - T_perturb)
        if let Some(trigger_time) = buf.friction_triggered_at {
            let mut current_time = 0;
            let mut pre_trigger_speed = 0.0;
            let mut found_trigger = false;
            
            for i in 1..payload_obj.events.len() {
                let e = &payload_obj.events[i];
                current_time += e.dt as u32;
                
                let dx = e.x as f32;
                let dy = e.y as f32;
                let dt = e.dt as f32;
                let speed = if dt > 0.0 { (dx*dx + dy*dy).sqrt() / dt } else { 0.0 };
                
                if !found_trigger && current_time >= trigger_time {
                    found_trigger = true;
                    pre_trigger_speed = speed;
                } else if found_trigger {
                    // Check for sudden drop in velocity or surge in force/radius | 检查速度是否骤降，或力度/半径是否激增
                    let force_change = (e.force as i16 - payload_obj.events[i-1].force as i16).abs();
                    let radius_change = (e.radius as i16 - payload_obj.events[i-1].radius as i16).abs();
                    
                    if speed < pre_trigger_speed * 0.5 || force_change > 30 || radius_change > 10 {
                        payload_obj.delta_react = Some((current_time - trigger_time) as i32);
                        break;
                    }
                }
            }
        }
        buf.reset(); // Secure wipe
    });

    // 1. Decode Server Materials | 1. 解码服务端材料
    let server_pub_bytes = BASE64.decode(server_pub_key_b64).map_err(|_| JsValue::from_str("Invalid server pub key"))?;
    let server_nonce_bytes = BASE64.decode(server_nonce_b64).map_err(|_| JsValue::from_str("Invalid server nonce"))?;
    
    if server_pub_bytes.len() != 32 {
        return Err(JsValue::from_str("Invalid pub key length"));
    }
    
    let mut pub_key_arr = [0u8; 32];
    pub_key_arr.copy_from_slice(&server_pub_bytes[0..32]);
    let server_pub = PublicKey::from(pub_key_arr);
    
    // 2. Generate Client Keypair (X25519) | 2. 生成客户端密钥对 (X25519)
    let client_secret = StaticSecret::random_from_rng(OsRng);
    let client_pub = PublicKey::from(&client_secret);
    
    // 3. ECDH Key Agreement | 3. ECDH 密钥协商
    let shared_secret = client_secret.diffie_hellman(&server_pub);
    
    // 4. HKDF Entropy Pool (Server Nonce + Shared Secret + JS Entropy) | 4. HKDF 熵池 (服务端 Nonce + 共享密钥 + JS 熵)
    let hkdf = Hkdf::<Sha256>::new(Some(&server_nonce_bytes), shared_secret.as_bytes());
    let mut okm = [0u8; 32 + 12 + 32]; // 32 bytes for AES Key, 12 bytes for IV, 32 bytes for Client Sign Nonce
    hkdf.expand(js_entropy.as_bytes(), &mut okm).map_err(|_| JsValue::from_str("HKDF expansion failed"))?;
    
    let aes_key = &okm[0..32];
    let aes_iv = &okm[32..44];
    payload_obj.client_sign_nonce = BASE64.encode(&okm[44..76]);
    
    // V14 HMAC Verification Implementation | V14 HMAC 验证实现
    let mut mac = Hmac::<Sha256>::new_from_slice(aes_key).map_err(|_| JsValue::from_str("HMAC init failed"))?;
    for e in &payload_obj.events {
        mac.update(&e.x.to_le_bytes());
        mac.update(&e.dt.to_le_bytes());
    }
    payload_obj.event_mac = hex::encode(mac.finalize().into_bytes());
    
    let payload_json = serde_json::to_string(&payload_obj).map_err(|_| JsValue::from_str("Serialization failed"))?;
    
    // 5. AES-256-GCM Encryption | 5. AES-256-GCM 加密
    let cipher = Aes256Gcm::new(aes_key.into());
    let nonce = Nonce::from_slice(aes_iv);
    
    let ciphertext = cipher.encrypt(nonce, payload_json.as_bytes())
        .map_err(|_| JsValue::from_str("Encryption failed"))?;
        
    #[derive(Serialize)]
    struct Wrapper {
        client_pub: String,
        ciphertext: String,
    }
    
    let wrapper = Wrapper {
        client_pub: BASE64.encode(client_pub.as_bytes()),
        ciphertext: BASE64.encode(ciphertext),
    };
    
    Ok(serde_json::to_string(&wrapper).unwrap())
}
