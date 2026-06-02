FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

ENV DM_HOST=0.0.0.0
ENV DM_PORT=5000
ENV DM_DB_PATH=/data/domain_manager.db

EXPOSE 5000

# 运行时请通过环境变量提供 SECRET_KEY 和 DM_ENCRYPTION_KEY。
CMD ["python", "run.py"]
