FROM python:3.12-slim

WORKDIR /app/api

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN mkdir -p /app/api/storage/input /app/api/storage/output

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
