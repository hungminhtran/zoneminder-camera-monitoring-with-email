FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DB_PATH=/data/zoneminder_monitoring.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/
COPY apexcharts-js/ /app/apexcharts-js/

EXPOSE 9080

CMD ["uvicorn", "web:app", "--host", "0.0.0.0", "--port", "9080"]
