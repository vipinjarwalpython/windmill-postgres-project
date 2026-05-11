# services/notify/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/          /app/config/
COPY services/notify/notify.py /app/notify.py

CMD ["python", "notify.py"]
