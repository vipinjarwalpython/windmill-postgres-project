# services/process_data/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/          /app/config/
COPY services/process_data/process_data.py /app/process_data.py

CMD ["python", "process_data.py"]
