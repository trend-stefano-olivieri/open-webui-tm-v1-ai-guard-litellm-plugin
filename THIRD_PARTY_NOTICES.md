# Third-party notices

This repository integrates, but does not claim ownership of, the following projects.

## TrendAI Vision One LiteLLM Guardrail Plugin

- Source: https://github.com/trendmicro/tm-v1-ai-guard-litellm-plugin
- Pinned submodule release: `v0.1.1`
- License: Apache License 2.0
- License text: [`vendor/tm-v1-ai-guard-litellm-plugin/LICENSE`](vendor/tm-v1-ai-guard-litellm-plugin/LICENSE)

The submodule retains its upstream history and license.

## OpenWebUI

- Source: https://github.com/open-webui/open-webui
- Default image used by this repository: `ghcr.io/open-webui/open-webui:v0.11.0`
- License: Open WebUI License, with older materials governed by the terms described in the upstream `LICENSE_HISTORY`
- License copy: [`LICENSES/Open-WebUI-License.txt`](LICENSES/Open-WebUI-License.txt)

The derived image applies a minimal compatibility patch. OpenWebUI branding is not removed or altered.

## LiteLLM

- Source: https://github.com/BerriAI/litellm
- Image: `docker.litellm.ai/berriai/litellm:main-stable`
- License information: https://github.com/BerriAI/litellm/blob/main/LICENSE

## Ollama

- Source: https://github.com/ollama/ollama
- Image: `ollama/ollama:latest`
- License information: https://github.com/ollama/ollama/blob/main/LICENSE

## ModernBERT zero-shot classifier

- Source: https://huggingface.co/MoritzLaurer/ModernBERT-base-zeroshot-v2.0
- Pinned revision: `d421c4545a438fd006fb43f8b981c5d908faa1e1`
- License: Apache License 2.0

The model weights are downloaded when the local `topic-guard` image is built and remain subject to the model publisher's terms.

## MiniLM NLI grounding classifier

- Source: https://huggingface.co/cross-encoder/nli-MiniLM2-L6-H768
- Pinned revision: `b95119ce93d3e065de6214e38cd4a97b0f2f2c6d`
- License: Apache License 2.0

The model weights are downloaded when the local `topic-guard` image is built and remain subject to the model publisher's terms.

## Topic-guard runtime dependencies

- [PyTorch](https://github.com/pytorch/pytorch) — BSD-style license
- [Hugging Face Transformers](https://github.com/huggingface/transformers) — Apache License 2.0
- [FastAPI](https://github.com/fastapi/fastapi) — MIT License
- [Uvicorn](https://github.com/encode/uvicorn) — BSD 3-Clause License
- [PyYAML](https://github.com/yaml/pyyaml) — MIT License

Container images and downloaded model weights are distributed separately by their respective publishers and remain subject to their own terms.
