# services/load_data/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy shared config + this service
COPY config/          /app/config/
COPY services/load_data/load_data.py /app/load_data.py

CMD ["python", "load_data.py"]
