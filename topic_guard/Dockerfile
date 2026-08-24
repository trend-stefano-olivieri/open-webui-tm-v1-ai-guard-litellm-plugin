FROM python:3.12.11-slim-bookworm

ARG TOPIC_MODEL_ID=MoritzLaurer/ModernBERT-base-zeroshot-v2.0
ARG TOPIC_MODEL_REVISION=d421c4545a438fd006fb43f8b981c5d908faa1e1
ARG GROUNDING_MODEL_ID=cross-encoder/nli-MiniLM2-L6-H768
ARG GROUNDING_MODEL_REVISION=b95119ce93d3e065de6214e38cd4a97b0f2f2c6d

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOPIC_MODEL_PATH=/models/topic-model \
    TOPIC_POLICY_PATH=/app/policies/topics.yaml \
    GROUNDING_MODEL_PATH=/models/grounding-model \
    GROUNDING_POLICY_PATH=/app/policies/grounding.yaml

WORKDIR /app

COPY topic_guard/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.7.1 \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt

COPY topic_guard/download_model.py /tmp/download_model.py
RUN TRANSFORMERS_OFFLINE=0 HF_HOME=/tmp/hf-cache python /tmp/download_model.py \
      --model "${TOPIC_MODEL_ID}" \
      --revision "${TOPIC_MODEL_REVISION}" \
      --output "${TOPIC_MODEL_PATH}" \
    && TRANSFORMERS_OFFLINE=0 HF_HOME=/tmp/hf-cache python /tmp/download_model.py \
      --model "${GROUNDING_MODEL_ID}" \
      --revision "${GROUNDING_MODEL_REVISION}" \
      --output "${GROUNDING_MODEL_PATH}" \
    && rm -rf /tmp/hf-cache /tmp/download_model.py

COPY topic_guard /app/topic_guard
COPY grounding /app/grounding
COPY policies /app/policies

RUN useradd --create-home --uid 10001 topicguard \
    && chown -R topicguard:topicguard /app /models
USER topicguard

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "topic_guard.app:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
