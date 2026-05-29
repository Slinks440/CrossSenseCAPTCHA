import pytest
from src.backend.detector import AttackerDetector

@pytest.fixture
def detector():
    return AttackerDetector()

def test_missing_delta_react(detector):
    is_bot, risk, reason = detector.analyze_behavior(1000, {"events": []})
    assert is_bot is True
    assert reason == "missing_biological_delta"

def test_invalid_delta_react(detector):
    is_bot, risk, reason = detector.analyze_behavior(1000, {"delta_react": 50, "events": []})
    assert is_bot is True
    assert "instant_ai_injection" in reason

def test_insufficient_events(detector):
    is_bot, risk, reason = detector.analyze_behavior(1000, {"delta_react": 300, "events": [{"x": 1, "y": 1, "dt": 1}]})
    assert is_bot is True
    assert reason == "insufficient_telemetry_events"

def test_human_verified(detector):
    # Construct a valid event stream mimicking a human
    events = [
        {"x": 10, "y": 10, "dt": 16, "force": 10, "radius": 5},
        {"x": 50, "y": 50, "dt": 16, "force": 10, "radius": 5},   # Fast movement (pre_reaction_speed high)
        {"x": 55, "y": 55, "dt": 100, "force": 30, "radius": 15}, # Velocity drop (reaction_speed) & Force surge
        {"x": 65, "y": 65, "dt": 16, "force": 30, "radius": 15},  # Secondary accel
        {"x": 66, "y": 66, "dt": 16, "force": 30, "radius": 15},  # Padding
        {"x": 67, "y": 67, "dt": 16, "force": 30, "radius": 15},  # Padding
    ]
    logic_data = {
        "delta_react": 300,
        "events": events
    }
    is_bot, risk, reason = detector.analyze_behavior(1000, logic_data, is_touch=True)
    assert is_bot is False
    assert reason == "human_verified"

def test_missing_touch_surge(detector):
    # Construct a valid event stream mimicking a human, but lacking force surge for a touch device
    events = [
        {"x": 10, "y": 10, "dt": 16, "force": 10, "radius": 5},
        {"x": 50, "y": 50, "dt": 16, "force": 10, "radius": 5},   
        {"x": 55, "y": 55, "dt": 100, "force": 10, "radius": 5}, # Velocity drop but no surge
        {"x": 65, "y": 65, "dt": 16, "force": 10, "radius": 5},  
        {"x": 66, "y": 66, "dt": 16, "force": 10, "radius": 5},  
        {"x": 67, "y": 67, "dt": 16, "force": 10, "radius": 5},  
    ]
    logic_data = {
        "delta_react": 300,
        "events": events
    }
    is_bot, risk, reason = detector.analyze_behavior(1000, logic_data, is_touch=True)
    assert is_bot is True
    assert reason == "missing_physical_momentum_compensation"
