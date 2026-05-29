# Stage 1: Build Rust extension | 阶段 1：构建 Rust 扩展
FROM python:3.10-slim as builder

# Install Rust toolchain and dependencies | 安装 Rust 工具链及依赖
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install maturin

# Build the pow_ext | 构建 pow_ext 扩展
COPY src/backend/pow_ext /app/src/backend/pow_ext
WORKDIR /app/src/backend/pow_ext
RUN maturin build --release --out /wheels

# Stage 2: Final runtime | 阶段 2：最终运行环境
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for audio/image processing | 安装音视频处理系统依赖
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the built Rust extension | 安装已构建的 Rust 扩展
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl

# Copy application source | 复制应用源代码
COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY dataset/raw_assets /app/dataset/raw_assets

# Environment setup | 环境变量设置
ENV FLASK_APP=src.backend.app:app
ENV FLASK_ENV=production

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "src.backend.app:app"]
