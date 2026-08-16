# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System libraries required by opencv-headless, cairosvg (SVG), and PyMuPDF (PDF).
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      libglib2.0-0 \
      libgl1 \
      libcairo2 \
      libpango-1.0-0 \
      libpangocairo-1.0-0 \
      libgdk-pixbuf-2.0-0 \
      shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Torch comes from the CPU index: the default wheel pulls ~2GB of CUDA payload
# that a CPU-only container never uses.
COPY requirements.txt requirements-llm.txt ./
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu \
         torch==2.12.0 torchvision==0.27.0 \
    && grep -vE '^(torch|torchvision)==' requirements.txt > /tmp/rest.txt \
    && pip install -r /tmp/rest.txt

# Real LLM provider SDKs are opt-in: they are only needed when LLM_PROVIDER is
# anthropic/openai/gemini, and google-generativeai alone pulls a large tree.
# Enable with: INSTALL_LLM_SDKS=true docker compose build api
ARG INSTALL_LLM_SDKS=false
RUN if [ "$INSTALL_LLM_SDKS" = "true" ]; then \
        pip install -r requirements-llm.txt ; \
    fi

COPY app ./app
COPY tests ./tests

RUN mkdir -p /app/storage

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=5 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
