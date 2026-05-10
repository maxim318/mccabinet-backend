FROM python:3.11-slim

RUN apt-get update && apt-get install -y poppler-utils

WORKDIR /app
COPY . /app

RUN pip install -r requirements.txt

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
