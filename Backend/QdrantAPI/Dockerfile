FROM python:3.11-alpine
 
# Installera systemberoenden
RUN apk add --no-cache \
    chromium \
    chromium-chromedriver \
    bash \
    curl \
    ca-certificates \
    libstdc++ \
    ttf-freefont
 
# Kopiera API_KEYS.env-filen
COPY app/data/API_KEYS.env /app/data/API_KEYS.env

COPY app /app

# Kopiera och installera beroenden från requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Installera Python-bibliotek
RUN pip install --no-cache-dir selenium requests
 
# Sätt miljövariabler för Chromium
ENV CHROME_BIN=/usr/bin/chromium-browser \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    PYTHONUNBUFFERED=1
 
# Skapa arbetskatalog
WORKDIR /app

EXPOSE 3004
 
# Kör scriptet
CMD ["uvicorn", "qdrant_api:asgi_app", "--host", "0.0.0.0", "--port", "3004"]