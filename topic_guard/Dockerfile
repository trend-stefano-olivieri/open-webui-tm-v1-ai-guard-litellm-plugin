FROM python:3.12.11-slim-bookworm

ARG TOPIC_MODEL_ID=MoritzLaurer/ModernBERT-base-zeroshot-v2.0
ARG TOPIC_MODEL_REVISION=d421c4545a438fd006fb43f8b981c5d908faa1e1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOPIC_MODEL_PATH=/models/topic-model \
    TOPIC_POLICY_PATH=/app/policies/topics.yaml

WORKDIR /app

COPY topic_guard/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.7.1 \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt

COPY topic_guard/download_model.py /tmp/download_model.py
RUN TRANSFORMERS_OFFLINE=0 python /tmp/download_model.py \
      --model "${TOPIC_MODEL_ID}" \
      --revision "${TOPIC_MODEL_REVISION}" \
      --output "${TOPIC_MODEL_PATH}" \
    && rm /tmp/download_model.py

COPY topic_guard /app/topic_guard
COPY policies /app/policies

RUN useradd --create-home --uid 10001 topicguard \
    && chown -R topicguard:topicguard /app /models
USER topicguard

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "topic_guard.app:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
