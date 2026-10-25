FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    DB_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/
COPY apexcharts-js/ /app/apexcharts-js/
COPY tools/ /app/tools/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 9080

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "web:app", "--host", "0.0.0.0", "--port", "9080"]
