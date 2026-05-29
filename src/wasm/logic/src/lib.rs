use wasm_bindgen::prelude::*;
use std::cell::RefCell;
use serde::{Deserialize, Serialize};
use sha2::{Sha256, Digest};

#[wasm_bindgen(start)]
pub fn main() {
    console_error_panic_hook::set_once();
}

const MAX_EVENTS: usize = 1024;
const FRICTION_RADIUS: f32 = 50.0;

#[derive(Clone, Copy, Default, Debug, Serialize)]
struct TouchEvent {
    x: i16,
    y: i16,
    dt: u16,
    force: u8,
    radius: u8,
}

struct RingBuffer {
    events: [TouchEvent; MAX_EVENTS],
    head: usize,
    count: usize,
    friction_triggered_at: Option<u32>,
    total_time: u32,
    last_x: f32,
    last_y: f32,
    target_x: f32,
    target_y: f32,
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
            target_x: 0.0,
            target_y: 0.0,
        }
    }

    fn push(&mut self, x: f32, y: f32, dt: f32, force: f32, radius: f32) {
        let dt_u16 = dt.clamp(0.0, 65535.0) as u16;
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
}

thread_local! {
    static BUFFER: RefCell<RingBuffer> = RefCell::new(RingBuffer::new());
    static EVENT_MAC: RefCell<Sha256> = RefCell::new(Sha256::new());
}

#[wasm_bindgen]
pub fn set_friction_target(obfuscated_x: u32, obfuscated_y: u32, seed_num: u32) {
    let x = (obfuscated_x ^ seed_num) as f32;
    let y = (obfuscated_y ^ seed_num) as f32;
    BUFFER.with(|b| {
        let mut buf = b.borrow_mut();
        buf.target_x = x;
        buf.target_y = y;
    });
}

#[wasm_bindgen]
pub fn push_event(x: f32, y: f32, dt: f32, force: f32, radius: f32) {
    BUFFER.with(|b| {
        let mut buf = b.borrow_mut();
        buf.push(x, y, dt, force, radius);
        
        let head_idx = if buf.head == 0 { MAX_EVENTS - 1 } else { buf.head - 1 };
        let event = buf.events[head_idx];
        
        EVENT_MAC.with(|m| {
            let mut mac = m.borrow_mut();
            mac.update(event.x.to_le_bytes());
            mac.update(event.y.to_le_bytes());
            mac.update(event.dt.to_le_bytes());
            mac.update(&[event.force]);
            mac.update(&[event.radius]);
        });
    });
}

#[wasm_bindgen]
pub fn check_friction_trigger(x: f32, y: f32) -> f32 {
    let mut coeff = 1.0;
    BUFFER.with(|b| {
        let mut buf = b.borrow_mut();
        let dx = x - buf.target_x;
        let dy = y - buf.target_y;
        let dist = (dx * dx + dy * dy).sqrt();
        
        if dist < FRICTION_RADIUS {
            if buf.friction_triggered_at.is_none() {
                buf.friction_triggered_at = Some(buf.total_time);
            }
            coeff = 1.8;
        }
    });
    coeff
}

#[derive(Serialize)]
struct ExtractedLogicData {
    events: Vec<TouchEvent>,
    delta_react: Option<i32>,
    event_mac: String,
}

#[wasm_bindgen]
pub fn extract_payload(is_touch: bool) -> Vec<u8> {
    let mut payload_obj = ExtractedLogicData {
        events: Vec::new(),
        delta_react: None,
        event_mac: String::new(),
    };

    BUFFER.with(|b| {
        let mut buf = b.borrow_mut();
        let mut events = Vec::with_capacity(buf.count);
        let start = if buf.count < MAX_EVENTS { 0 } else { buf.head };
        for i in 0..buf.count {
            events.push(buf.events[(start + i) % MAX_EVENTS]);
        }
        payload_obj.events = events;
        
        if let Some(trigger_time) = buf.friction_triggered_at {
            let buffer_duration: u32 = payload_obj.events.iter().map(|e| e.dt as u32).sum();
            let mut current_time = buf.total_time.saturating_sub(buffer_duration);
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
                    let mut is_reaction = speed < pre_trigger_speed * 0.5;
                    
                    if is_touch {
                        let prev_e = &payload_obj.events[i-1];
                        let force_change = (e.force as i16 - prev_e.force as i16).abs();
                        let radius_change = (e.radius as i16 - prev_e.radius as i16).abs();
                        if force_change > 30 || radius_change > 10 {
                            is_reaction = true;
                        }
                    }
                    
                    if is_reaction {
                        payload_obj.delta_react = Some((current_time - trigger_time) as i32);
                        break;
                    }
                }
            }
        }
        
        // Zero-fill internal state memory
        buf.events.fill(TouchEvent::default());
        buf.head = 0;
        buf.count = 0;
        buf.friction_triggered_at = None;
        buf.total_time = 0;
        buf.last_x = 0.0;
        buf.last_y = 0.0;
    });

    EVENT_MAC.with(|m| {
        let mut mac = m.borrow_mut();
        let result = mac.clone().finalize();
        *mac = Sha256::new();
        payload_obj.event_mac = hex::encode(result);
    });

    serde_json::to_vec(&payload_obj).unwrap_or_default()
}
