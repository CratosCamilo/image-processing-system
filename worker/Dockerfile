FROM python:3.12-slim

WORKDIR /app/worker

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN mkdir -p /app/api/storage/input /app/api/storage/output

CMD ["python", "worker.py"]
