# services/store_data/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/          /app/config/
COPY services/store_data/store_data.py /app/store_data.py

CMD ["python", "store_data.py"]
