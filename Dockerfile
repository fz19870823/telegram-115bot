FROM python:3.11-slim

# 运行时优化环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 设置工作目录
WORKDIR /app

# 复制依赖并安装
COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check --no-compile -r requirements.txt

# 复制应用文件
COPY . .

# 容器启动时会使用外部传入的环境变量 TELEGRAM_BOT_TOKEN
CMD ["python", "bot.py"]
