FROM python:3.11

# Ange arbetskatalogen som /app
WORKDIR /app

# Kopiera beroenden och installera dem
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y chromium chromium-driver

# Kopiera hela projektet till containern
COPY . .

# Byt arbetskatalog till src, där Python-skriptet finns
WORKDIR /app/src

# Exponera port 3003
EXPOSE 3004

# Starta Python-skriptet
CMD ["uvicorn", "qdrant_api:asgi_app", "--host", "0.0.0.0", "--port", "3004", "--reload"]

