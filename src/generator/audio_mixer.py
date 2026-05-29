from pydub import AudioSegment
try:
    from pydub.generators import WhiteNoise, Sine, Square
except ImportError:
    WhiteNoise = Sine = Square = None
import os
import random


class AudioMixer:
    def __init__(self):
        self.rng = random.SystemRandom()

    def create_sequence(self, _, selected_audios, start_times, output_path):
        events = []
        max_end_time = 0

        for audio_path, start_sec in zip(selected_audios, start_times):
            if not os.path.exists(audio_path):
                continue
            try:
                sound = AudioSegment.from_file(audio_path)
                end_sec = start_sec + (len(sound) / 1000.0)
                if end_sec > max_end_time:
                    max_end_time = end_sec
            except Exception:
                pass

        duration_sec = max_end_time + 1.0
        duration_ms = int(duration_sec * 1000)
        base_audio = AudioSegment.silent(duration=duration_ms)

        if WhiteNoise and Sine and Square:
            # Generate complex environmental noise (like cocktail party or factory hum) | 生成复杂的环境噪声（如鸡尾酒会或工厂噪音）
            noise_base = WhiteNoise().to_audio_segment(duration=duration_ms).apply_gain(-25)
            
            # Combine random frequency sine/square waves to simulate voices/machines | 混合随机频率的正弦波/方波以模拟人声/机器声
            num_oscillators = self.rng.randint(3, 8)
            for _ in range(num_oscillators):
                freq = self.rng.randint(100, 3000)
                if self.rng.choice([True, False]):
                    osc = Sine(freq).to_audio_segment(duration=duration_ms).apply_gain(self.rng.uniform(-35, -20))
                else:
                    osc = Square(freq).to_audio_segment(duration=duration_ms).apply_gain(self.rng.uniform(-40, -25))
                noise_base = noise_base.overlay(osc)
            
            # Dynamic Signal-to-Noise Ratio (SNR) ±10dB | 动态信噪比 (SNR) ±10dB
            dynamic_gain = self.rng.uniform(-10, 10)
            noise_base = noise_base.apply_gain(dynamic_gain)
            
            if self.rng.choice([True, False]):
                noise_base = noise_base.low_pass_filter(self.rng.randint(1000, 4000))
            else:
                noise_base = noise_base.high_pass_filter(self.rng.randint(200, 600))
                
            base_audio = base_audio.overlay(noise_base)

        for audio_path, start_sec in zip(selected_audios, start_times):
            start_ms = int(start_sec * 1000)
            if not os.path.exists(audio_path):
                continue

            try:
                sound = AudioSegment.from_file(audio_path)
                sound = self._time_pitch_jitter(sound)
                sound = sound.high_pass_filter(self.rng.randint(60, 220))
                sound = sound.low_pass_filter(self.rng.randint(3400, 8200))
                sound = sound.apply_gain(self.rng.uniform(-5.0, -1.0))
                sound = sound.fade_in(self.rng.randint(20, 80)).fade_out(self.rng.randint(20, 90))
                base_audio = base_audio.overlay(sound, position=start_ms)
                source_id = os.path.splitext(os.path.basename(audio_path))[0].lower()
                events.append({"source": source_id, "start_time": start_sec})
            except Exception as e:
                print(f"Mix failed {audio_path}: {e}")

        base_audio.export(output_path, format="wav")

        return {
            "duration": duration_sec,
            "events": events,
        }

    def _time_pitch_jitter(self, sound):
        factor = self.rng.uniform(0.96, 1.04)
        shifted = sound._spawn(
            sound.raw_data,
            overrides={"frame_rate": int(sound.frame_rate * factor)},
        )
        return shifted.set_frame_rate(sound.frame_rate)
