import pytest
from src.backend.validator import AnswerValidator

def test_check_click_valid():
    validator = AnswerValidator(tolerance=5)
    bbox = [10, 10, 20, 20]
    assert validator.check_click(bbox, 15, 15) is True
    assert validator.check_click(bbox, 10, 10) is True
    assert validator.check_click(bbox, 25, 25) is True # within tolerance
    assert validator.check_click(bbox, 26, 26) is False # outside tolerance

def test_check_click_invalid_bbox():
    validator = AnswerValidator(tolerance=5)
    assert validator.check_click([], 15, 15) is False
    assert validator.check_click(None, 15, 15) is False
    assert validator.check_click([10, 20, 10, 20], 15, 15) is False # invalid bbox shape (x2 <= x1)

def test_check_click_bad_data_types():
    validator = AnswerValidator(tolerance=5)
    assert validator.check_click(["a", "b", "c", "d"], 15, 15) is False
    assert validator.check_click([10, 10, 20, 20], "a", "b") is False
