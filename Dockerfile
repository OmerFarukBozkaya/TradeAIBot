# syntax=docker/dockerfile:1
FROM python:3.11-slim

ARG INSTALL_AI=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Istanbul

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc build-essential curl tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ai.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

RUN if [ "$INSTALL_AI" = "true" ]; then pip install -r requirements-ai.txt; fi

COPY . .

RUN mkdir -p Data Log state Trade_Durumu Trade_Durumu_AI

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
