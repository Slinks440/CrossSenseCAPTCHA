from PIL import Image, ImageDraw, ImageEnhance
import os
import random

RESAMPLING = getattr(Image, "Resampling", Image)
TRANSFORM = getattr(Image, "Transform", Image)


class ImageComposer:
    def __init__(self, canvas_size=(600, 300)):
        self.canvas_size = canvas_size
        self.rng = random.SystemRandom()

    def generate_captcha_image(self, selected_images, output_path):
        canvas_w, canvas_h = self.canvas_size
        canvas = self._create_noisy_background(canvas_w, canvas_h)

        image_metadata = []
        placed_boxes = []

        for img_path in selected_images:
            if not os.path.exists(img_path):
                continue

            try:
                animal_img = Image.open(img_path).convert("RGBA")
                animal_img = self._prepare_object(animal_img)
                x, y = self._choose_position(animal_img.size, placed_boxes)

                canvas.paste(animal_img, (x, y), mask=animal_img)

                target_w, target_h = animal_img.size
                bbox = [x, y, x + target_w, y + target_h]
                placed_boxes.append(bbox)
                label = os.path.basename(os.path.dirname(img_path)).lower()
                image_metadata.append({"label": label, "bbox": bbox})
            except Exception as e:
                print(f"Paste failed {img_path}: {e}")

        self._draw_foreground_noise(canvas)
        canvas.save(output_path)
        return image_metadata

    def _prepare_object(self, animal_img):
        canvas_w, canvas_h = self.canvas_size
        max_w = self.rng.randint(115, 165)
        max_h = self.rng.randint(105, 165)
        max_w = min(max_w, canvas_w // 3)
        max_h = min(max_h, canvas_h - 30)

        img_ratio = animal_img.width / animal_img.height
        target_w = max_w
        target_h = int(max_w / img_ratio)
        if target_h > max_h:
            target_h = max_h
            target_w = int(max_h * img_ratio)

        animal_img = animal_img.resize((target_w, target_h), RESAMPLING.LANCZOS)
        animal_img = self._jitter_color(animal_img)
        animal_img = self._affine_warp(animal_img)
        animal_img = animal_img.rotate(
            self.rng.uniform(-18, 18),
            expand=True,
            resample=RESAMPLING.BICUBIC,
            fillcolor=(0, 0, 0, 0),
        )
        return animal_img

    def _jitter_color(self, img):
        rgb = img.convert("RGB")
        alpha = img.getchannel("A")
        rgb = ImageEnhance.Brightness(rgb).enhance(self.rng.uniform(0.82, 1.18))
        rgb = ImageEnhance.Contrast(rgb).enhance(self.rng.uniform(0.82, 1.22))
        rgb = ImageEnhance.Color(rgb).enhance(self.rng.uniform(0.75, 1.35))

        overlay = Image.new(
            "RGB",
            rgb.size,
            (
                self.rng.randint(0, 255),
                self.rng.randint(0, 255),
                self.rng.randint(0, 255),
            ),
        )
        rgb = Image.blend(rgb, overlay, self.rng.uniform(0.04, 0.12))
        return Image.merge("RGBA", (*rgb.split(), alpha))

    def _affine_warp(self, img):
        w, h = img.size
        shear_x = self.rng.uniform(-0.16, 0.16)
        shear_y = self.rng.uniform(-0.06, 0.06)
        extra_w = int(abs(shear_x) * h) + 6
        extra_h = int(abs(shear_y) * w) + 6
        new_w = w + extra_w
        new_h = h + extra_h
        x_offset = extra_w // 2
        y_offset = extra_h // 2

        return img.transform(
            (new_w, new_h),
            TRANSFORM.AFFINE,
            (1, shear_x, -x_offset, shear_y, 1, -y_offset),
            resample=RESAMPLING.BICUBIC,
            fillcolor=(0, 0, 0, 0),
        )

    def _choose_position(self, size, placed_boxes):
        canvas_w, canvas_h = self.canvas_size
        target_w, target_h = size
        max_x = max(10, canvas_w - target_w - 10)
        max_y = max(10, canvas_h - target_h - 10)

        best = None
        best_overlap = 1.0
        for _ in range(80):
            x = self.rng.randint(10, max_x)
            y = self.rng.randint(10, max_y)
            candidate = [x, y, x + target_w, y + target_h]
            overlap = max((self._box_iou(candidate, box) for box in placed_boxes), default=0.0)
            if overlap < 0.08:
                return x, y
            if overlap < best_overlap:
                best = (x, y)
                best_overlap = overlap

        if best:
            return best
        return self.rng.randint(10, max_x), self.rng.randint(10, max_y)

    def _box_iou(self, a, b):
        inter_x1 = max(a[0], b[0])
        inter_y1 = max(a[1], b[1])
        inter_x2 = min(a[2], b[2])
        inter_y2 = min(a[3], b[3])
        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h
        if inter_area == 0:
            return 0.0

        area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
        area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
        return inter_area / (area_a + area_b - inter_area)

    def _create_noisy_background(self, canvas_w, canvas_h):
        from PIL import ImageFilter
        base = (
            self.rng.randint(220, 250),
            self.rng.randint(220, 250),
            self.rng.randint(220, 250),
        )
        canvas = Image.new("RGB", self.canvas_size, base)
        
        # 产生高低频的程序化噪声纹理 (Value Noise 叠加) | Generate high/low frequency procedural noise texture (Value Noise overlay)
        # 1. 低频纹理 (粗大斑块) | 1. Low frequency texture (large patches)
        low_freq = Image.effect_noise((canvas_w // 8, canvas_h // 8), self.rng.randint(40, 100))
        low_freq = low_freq.filter(ImageFilter.GaussianBlur(self.rng.uniform(1.0, 3.0)))
        low_freq = low_freq.resize(self.canvas_size, RESAMPLING.BICUBIC)
        
        # 2. 中频纹理 (细碎波纹) | 2. Mid frequency texture (fine ripples)
        mid_freq = Image.effect_noise((canvas_w // 3, canvas_h // 3), self.rng.randint(30, 80))
        mid_freq = mid_freq.filter(ImageFilter.GaussianBlur(self.rng.uniform(0.5, 1.5)))
        mid_freq = mid_freq.resize(self.canvas_size, RESAMPLING.BICUBIC)
        
        # 混合成颜色遮罩 | Mix into color mask
        layer1 = Image.new("RGBA", self.canvas_size, (self.rng.randint(50, 200), self.rng.randint(50, 200), self.rng.randint(50, 200), 255))
        layer2 = Image.new("RGBA", self.canvas_size, (self.rng.randint(50, 200), self.rng.randint(50, 200), self.rng.randint(50, 200), 255))
        
        canvas.paste(layer1, (0,0), low_freq)
        canvas.paste(layer2, (0,0), mid_freq)

        # 随机色彩扰动块 | Random color perturbation blocks
        draw = ImageDraw.Draw(canvas, "RGBA")
        for _ in range(self.rng.randint(15, 30)):
            x0 = self.rng.randint(-50, canvas_w)
            y0 = self.rng.randint(-50, canvas_h)
            x1 = x0 + self.rng.randint(50, 200)
            y1 = y0 + self.rng.randint(50, 200)
            color = (self.rng.randint(0, 255), self.rng.randint(0, 255), self.rng.randint(0, 255), self.rng.randint(20, 60))
            draw.ellipse((x0, y0, x1, y1), fill=color)

        return canvas

    def _draw_foreground_noise(self, canvas):
        from PIL import ImageFilter
        canvas_w, canvas_h = self.canvas_size
        
        # 叠加半透明的高频随机碎片和非线性扭曲 | Overlay semi-transparent high-frequency random fragments and non-linear distortion
        noise_layer = Image.new("RGBA", self.canvas_size, (0,0,0,0))
        draw = ImageDraw.Draw(noise_layer)
        
        for _ in range(self.rng.randint(40, 80)):
            x = self.rng.randint(-20, canvas_w)
            y = self.rng.randint(-20, canvas_h)
            pts = []
            for _ in range(self.rng.randint(3, 6)):
                pts.append((x + self.rng.randint(-30, 30), y + self.rng.randint(-30, 30)))
            color = (self.rng.randint(50, 200), self.rng.randint(50, 200), self.rng.randint(50, 200), self.rng.randint(10, 80))
            draw.polygon(pts, fill=color)
        
        # 对覆盖层做稍微模糊，使之与环境融合 | Slightly blur the overlay to blend with the environment
        noise_layer = noise_layer.filter(ImageFilter.GaussianBlur(self.rng.uniform(0.5, 1.5)))
        canvas.paste(noise_layer, (0, 0), noise_layer)

        # FGSM-like 的全局微小梯度扰动（纯数学计算）：对原图像像素进行颜色偏置，干扰神经网络卷积提取 | FGSM-like global minor gradient perturbation: offset pixel colors to disrupt NN convolution
        # 使用快速的 point function 对比度非线性偏移 | Use fast point function for non-linear contrast offset
        r, g, b = canvas.split()
        r = r.point(lambda i: max(0, min(255, i + self.rng.randint(-15, 15))))
        g = g.point(lambda i: max(0, min(255, i + self.rng.randint(-15, 15))))
        b = b.point(lambda i: max(0, min(255, i + self.rng.randint(-15, 15))))
        canvas.paste(Image.merge("RGB", (r, g, b)))

