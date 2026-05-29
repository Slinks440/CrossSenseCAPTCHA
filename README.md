# CrossSenseCAPTCHA (跨感官验证码)

[English](#english) | [中文](#chinese)

---

<h2 id="english">English</h2>

CrossSenseCAPTCHA is a highly secure, cross-sensory (audio + visual) CAPTCHA system designed to defeat automated bots through cognitive challenges, end-to-end payload encryption, and client environment detection.

### Features
- **Cross-Sensory Challenges**: Users are asked to identify objects based on auditory cues (e.g., clicking the object that made a specific sound, or the one that made no sound).
- **Proof-of-Work (PoW)**: Uses a Rust-based WebAssembly and PyO3 extension to mandate computational work from the client, mitigating DDoS and spam.
- **End-to-End Encryption**: Utilizes X25519 key exchange and AES-GCM to encrypt payloads between the WebAssembly frontend and the Python backend.
- **Memory Tamper Detection**: Validates interaction events via HMAC to prevent automated script injection.
- **Asynchronous Generation**: Captchas are pre-generated using a Celery worker pool and stored in Redis, ensuring high throughput and low API latency.
- **Dynamic Obfuscation**: The target coordinates are obfuscated using a server nonce, defeating static analysis of the frontend memory.

### Architecture
- **Backend**: Python (Flask, Celery, Redis, Cryptography).
- **Frontend**: HTML5, JS, WebAssembly (Rust).
- **PoW Engine**: Rust (PyO3).
- **Telemetry**: Kafka.

### Prerequisites
- Python 3.9+
- Redis Server
- Kafka Broker (Optional, for telemetry)
- Rust Toolchain (cargo) to build the extensions

### Quick Start
#### 1. Clone & Environment
```bash
git clone <repository_url>
cd CrossSenseCAPTCHA
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 2. Configuration
Copy `.env.example` to `.env` and fill in the secrets:
```bash
cp .env.example .env
```
Ensure you have a strong `JWT_SECRET`.

#### 3. Build Rust Extensions
You must build the PoW Python extension:
```bash
cd src/backend/pow_ext
maturin develop --release
cd ../../../
```
*(Note: Building the Wasm frontend requires `wasm-pack`)*

#### 4. Run Services
Start Redis (if not using Docker):
```bash
redis-server
```
Start the Celery worker for CAPTCHA generation:
```bash
celery -A src.backend.celery_app worker --loglevel=info
```
Start the Flask Backend:
```bash
python src/backend/app.py
```

#### 5. Docker Compose (Recommended)
You can launch the entire stack (Redis, Backend, Celery) via Docker:
```bash
docker-compose up --build
```

### License
MIT License. See [LICENSE](LICENSE) for details.

---

<h2 id="chinese">中文</h2>

CrossSenseCAPTCHA 是一款高安全性、跨感官（音频 + 视觉）的验证码系统，旨在通过认知挑战、端到端载荷加密以及客户端环境检测来抵御自动化机器人（Bot）。

### 特性
- **跨感官挑战**：要求用户基于听觉提示识别对象（例如：点击发出特定声音的物体，或者没有发出声音的物体）。
- **工作量证明 (PoW)**：使用基于 Rust 的 WebAssembly 和 PyO3 扩展，强制客户端进行计算工作，从而缓解 DDoS 和垃圾邮件攻击。
- **端到端加密**：利用 X25519 密钥交换和 AES-GCM 加密 WebAssembly 前端和 Python 后端之间的通信载荷。
- **内存防篡改检测**：通过 HMAC 验证交互事件流，防止自动化脚本直接注入坐标。
- **异步生成机制**：使用 Celery 工作池预先生成验证码并存储在 Redis 中，确保高并发吞吐量和极低的 API 延迟。
- **动态坐标混淆**：目标坐标使用服务器 Nonce 进行混淆，挫败对前端内存的静态分析。

### 架构
- **后端**：Python (Flask, Celery, Redis, Cryptography)。
- **前端**：HTML5, JS, WebAssembly (Rust)。
- **PoW 引擎**：Rust (PyO3)。
- **遥测**：Kafka。

### 前置要求
- Python 3.9+
- Redis Server
- Kafka Broker（可选，用于遥测）
- Rust Toolchain (cargo)，用于构建扩展

### 快速开始
#### 1. 克隆与环境配置
```bash
git clone <repository_url>
cd CrossSenseCAPTCHA
python -m venv venv
source venv/bin/activate  # Windows 环境使用: venv\Scripts\activate
pip install -r requirements.txt
```

#### 2. 配置
复制 `.env.example` 到 `.env` 并填写相关密钥：
```bash
cp .env.example .env
```
确保您设置了一个强密码的 `JWT_SECRET`。

#### 3. 构建 Rust 扩展
必须编译 PoW 的 Python 扩展：
```bash
cd src/backend/pow_ext
maturin develop --release
cd ../../../
```
*(注意：编译 Wasm 前端需要安装 `wasm-pack`)*

#### 4. 运行服务
启动 Redis（如果不使用 Docker）：
```bash
redis-server
```
启动用于生成验证码的 Celery Worker：
```bash
celery -A src.backend.celery_app worker --loglevel=info
```
启动 Flask 后端：
```bash
python src/backend/app.py
```

#### 5. Docker Compose (推荐)
您可以通过 Docker 启动完整的技术栈（Redis, 后端, Celery）：
```bash
docker-compose up --build
```

### 许可证
MIT License。详情请参阅 [LICENSE](LICENSE) 文件。
