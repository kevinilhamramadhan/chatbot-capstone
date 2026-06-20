FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 9000

CMD ["uvicorn", "mock_server:app", "--host", "0.0.0.0", "--port", "9000"]
