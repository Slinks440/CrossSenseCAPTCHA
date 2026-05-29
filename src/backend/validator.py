import math


class AnswerValidator:
    def __init__(self, tolerance=6):
        self.tolerance = tolerance

    def check_click(self, target_bbox, click_x, click_y):
        if not target_bbox or len(target_bbox) != 4:
            return False

        try:
            x1, y1, x2, y2 = [float(value) for value in target_bbox]
            click_x = float(click_x)
            click_y = float(click_y)
        except (TypeError, ValueError):
            return False

        values = (x1, y1, x2, y2, click_x, click_y)
        if not all(math.isfinite(value) for value in values):
            return False
        if x2 <= x1 or y2 <= y1:
            return False

        valid_x = (x1 - self.tolerance) <= click_x <= (x2 + self.tolerance)
        valid_y = (y1 - self.tolerance) <= click_y <= (y2 + self.tolerance)

        return valid_x and valid_y
