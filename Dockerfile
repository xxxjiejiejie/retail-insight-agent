FROM python:3.12-slim

ARG TORCH_VERSION=2.11.0
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir "torch==${TORCH_VERSION}" --index-url "${TORCH_INDEX_URL}" \
    && pip install --no-cache-dir ".[rag]"
COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
