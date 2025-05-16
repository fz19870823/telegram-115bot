FROM python:3.11-slim

# 安装必要依赖
RUN apt update && apt install -y curl && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用文件
COPY . .

# 容器启动时会使用外部传入的环境变量 TELEGRAM_BOT_TOKEN
CMD ["python", "bot.py"]
