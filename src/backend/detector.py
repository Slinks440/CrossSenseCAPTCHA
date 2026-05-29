import math
import logging

logger = logging.getLogger(__name__)

class AttackerDetector:
    def __init__(self):
        self.MIN_NEURAL_DELAY_MS = 150
        self.MAX_NEURAL_DELAY_MS = 600
        self.MIN_FORCE_SURGE = 15
        self.MIN_RADIUS_SURGE = 5
        self.VELOCITY_DROP_THRESHOLD = 0.5 
        self.SECONDARY_ACCEL_THRESHOLD = 1.2 

    def analyze_behavior(self, elapsed_time_ms, logic_data, is_touch=False, difficulty=1):
        """
        Validates the extracted logic data from Wasm. | 验证从 Wasm 提取的逻辑数据。
        Handles graceful degradation if `is_touch` is False. | 如果 `is_touch` 为 False，则进行优雅降级处理。
        """
        delta_react = logic_data.get("delta_react")
        if delta_react is None:
            return True, "HIGH", "missing_biological_delta"
            
        try: delta_react = int(delta_react)
        except (ValueError, TypeError): return True, "HIGH", "invalid_biological_delta"

        if delta_react < self.MIN_NEURAL_DELAY_MS:
            return True, "HIGH", f"instant_ai_injection_delta_{delta_react}ms"
        if delta_react > self.MAX_NEURAL_DELAY_MS:
            return True, "MEDIUM", f"unrealistic_neural_delay_{delta_react}ms"

        events = logic_data.get("events", [])
        if not events or len(events) < 5:
            return True, "HIGH", "insufficient_telemetry_events"
        
        max_force_surge = 0
        max_radius_surge = 0
        velocity_drop_found = False
        secondary_accel_found = False
        
        pre_reaction_speed = 0.0
        reaction_speed = 0.0
        
        abs_x, abs_y = 0, 0
        max_abs_x, max_abs_y = 0, 0
        min_abs_x, min_abs_y = 0, 0
        
        for i in range(len(events)):
            e = events[i]
            abs_x += e.get("x", 0)
            abs_y += e.get("y", 0)
            
            if abs_x > max_abs_x: max_abs_x = abs_x
            if abs_y > max_abs_y: max_abs_y = abs_y
            if abs_x < min_abs_x: min_abs_x = abs_x
            if abs_y < min_abs_y: min_abs_y = abs_y
            
            if i > 0:
                e1, e2 = events[i-1], events[i]
                dx, dy, dt = e2.get("x", 0), e2.get("y", 0), max(e2.get("dt", 1), 1)
                speed = math.hypot(dx, dy) / dt
                
                force_diff = abs(int(e2.get("force", 0)) - int(e1.get("force", 0)))
                radius_diff = abs(int(e2.get("radius", 0)) - int(e1.get("radius", 0)))
                
                if force_diff > max_force_surge: max_force_surge = force_diff
                if radius_diff > max_radius_surge: max_radius_surge = radius_diff
                    
                if not velocity_drop_found:
                    if pre_reaction_speed > 0 and speed < pre_reaction_speed * self.VELOCITY_DROP_THRESHOLD:
                        velocity_drop_found = True
                        reaction_speed = speed
                    else: pre_reaction_speed = max(pre_reaction_speed, speed)
                elif not secondary_accel_found:
                    if speed > reaction_speed * self.SECONDARY_ACCEL_THRESHOLD:
                        secondary_accel_found = True

        # V14 Fix: Absolute boundary check to prevent out-of-bounds affine replays | V14 修复：绝对边界检查，防止越界仿射重放
        if max_abs_x > 3000 or max_abs_y > 3000 or min_abs_x < -3000 or min_abs_y < -3000:
            return True, "HIGH", "unrealistic_absolute_movement_bounds"

        # V12 Graceful Degradation: If not a touch device, skip force/radius check | V12 优雅降级：如果不是触摸设备，则跳过按压力度/半径检查
        if is_touch:
            if max_force_surge < self.MIN_FORCE_SURGE and max_radius_surge < self.MIN_RADIUS_SURGE:
                return True, "HIGH", "missing_physical_momentum_compensation"
            
        if not velocity_drop_found or not secondary_accel_found:
            return True, "HIGH", "missing_kinetic_velocity_signature"

        return False, "LOW", "human_verified"
