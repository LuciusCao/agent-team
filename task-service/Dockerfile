FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY skill/ ./skill/

# 安装 task CLI 工具
RUN pip install --no-cache-dir requests && \
    chmod +x /app/skill/task

# 添加到 PATH
ENV PATH="/app/skill:${PATH}"
ENV TASK_SERVICE_URL=http://task-service:8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
