FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY qdrant_remove_diff.py .

CMD ["python", "qdrant_remove_diff.py"]