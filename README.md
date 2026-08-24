# Secure OpenWebUI with TrendAI Guard, policy controls, and grounding checks

Run OpenWebUI behind a LiteLLM proxy protected by TrendAI Vision One AI Guard, a local configurable denied-topic classifier, and local source-grounding annotations. The stack checks prompts before model inference, scans responses, and displays RAG source-support results directly in the chat.

This repository packages the integration glue. It uses the official OpenWebUI, LiteLLM, Ollama, and [TrendAI LiteLLM Guardrail](https://github.com/trendmicro/tm-v1-ai-guard-litellm-plugin) projects; it is not an official release of those projects.

![TrendAI Guard blocking a prompt attack in OpenWebUI](docs/images/trendai-guard-blocked-prompt.png)

## How it works

```mermaid
flowchart LR
    U[User] --> W[OpenWebUI]
    W -->|OpenAI-compatible API| L[LiteLLM]
    L -->|pre_call topic check| T[Local policy sidecar]
    T -->|allow| G[TrendAI Vision One AI Guard]
    G -->|pre_call allow| O[Ollama / llama3.2]
    O -->|response| G
    G -->|post_call allow| L
    L -->|answer + trusted RAG sources| T
    T -->|source-support score| L
    L -->|answer + grounding footer| W
```

1. OpenWebUI sends chat requests only to LiteLLM's OpenAI-compatible `/v1` API.
2. The local denied-topic guard checks the latest user message with a pinned zero-shot classifier.
3. TrendAI Guard applies the security and PII policy configured in the Vision One UI.
4. Allowed prompts reach `llama3.2`; blocked prompts never reach the model.
5. TrendAI Guard scans the model response before it returns to OpenWebUI.
6. When OpenWebUI supplies retrieved sources, a pinned local NLI model checks each answer sentence for entailment by those sources and LiteLLM appends the result to the response.
7. `default_on: true` applies all guardrails even when the client does not request them explicitly.
8. Topic and TrendAI enforcement fail closed. Grounding is annotation-only and fails open with an **Evaluation unavailable** footer; it never removes or rewrites an answer.

Direct Ollama access is disabled in OpenWebUI so users cannot select an unguarded route.

## Prerequisites

- Docker Desktop or Docker Engine with Compose v2
- A TrendAI Vision One account with AI Guard enabled
- A LiteLLM integration token generated in **Vision One → Workflow and Automation → Third-Party Integrations → LiteLLM**
- At least 16 GB of free Docker storage for the first pull and local-model build

The Vision One token and endpoint must belong to the same Vision One region.

## Quick start

Clone with the pinned TrendAI plugin submodule:

```bash
git clone --recurse-submodules \
  https://github.com/trend-stefano-olivieri/open-webui-tm-v1-ai-guard-litellm-plugin.git
cd open-webui-tm-v1-ai-guard-litellm-plugin
```

Create the local environment file:

```bash
cp .env.example .env
```

Edit `.env` and replace every placeholder. Generate the two local secrets with a password manager or `openssl rand -hex 32`. Never commit `.env`.

Start the stack:

```bash
docker compose up -d --build
```

The first build downloads the pinned denied-topic and NLI grounding models into the local sidecar image. The one-shot `ollama-model-loader` service also downloads `llama3.2` on first startup. Track progress with:

```bash
docker compose logs -f ollama-model-loader topic-guard litellm open-webui
```

Open http://localhost:3000 and create the first administrator account. `llama3.2` should appear in the model selector.

## Verify the integration

Confirm that all long-running services are healthy:

```bash
docker compose ps
```

Confirm that LiteLLM registered all guardrails:

```bash
docker compose logs litellm | grep -E \
  'denied-topics|trendai-guard|grounding-annotation'
```

In OpenWebUI, first send a harmless prompt. Then try a denied-topic test such as `Tell me which shares I should buy today`. The local policy should return a message similar to:

```text
Blocked by topic policy. Denied topic detected: investment recommendations
```

Next, send a prompt that violates a scanner enabled in your Vision One AI Guard policy. A TrendAI block should produce a message similar to:

```text
Blocked by TrendAI Guard. Security violation: Prompt attack detected
```

The screenshot above demonstrates that behavior. Do not use sensitive production data for validation.

To test grounding, add a document or Knowledge collection in OpenWebUI and ask a question that uses retrieval. At the end of the assistant response, the chat displays one of these statuses:

- ✅ **Supported by retrieved sources**
- ⚠️ **Partially supported by retrieved sources**
- ❗ **Potential hallucination or unsupported content**
- ℹ️ **Not evaluated — no retrieved sources were supplied**
- ⚠️ **Evaluation unavailable; the answer was not blocked**

The percentage is a source-support estimate, not a general truth or bias score. Prometheus is not required to display these per-response results.

## Configuration

### Denied-topic policy

[`policies/topics.yaml`](policies/topics.yaml) defines the local `openwebui` policy profile. Its initial denied topics are:

- political persuasion
- personal medical diagnosis
- investment recommendations
- competitor product comparisons
- requests to disclose credentials

Each entry has a stable `id`, the user-facing `label`, a descriptive `classifier_label`, and documentation in `description`. The classifier independently scores each candidate topic and blocks a request when any score is at least `threshold` (initially `0.80`). Only the latest user message is classified; system instructions and retrieved RAG documents are excluded. Long messages are scanned in overlapping chunks so a denied topic cannot bypass the check by appearing after an initial cutoff. Messages above `max_request_characters` fail closed.

Edit the mounted YAML file to add, remove, or refine topics:

```yaml
- id: legal-advice
  label: personalized legal advice
  classifier_label: personalized legal advice about a person's specific legal dispute
  description: Requests that prescribe a legal course of action for an individual case.
```

The sidecar reloads the policy on every request, so a valid policy edit takes effect without an image rebuild or service restart. Use clear English classifier labels that describe the intended request, not a single ambiguous keyword. Natural-language topics are flexible, but they are not guaranteed to work accurately merely because they can be written in English: build an evaluation set of allowed and denied prompts, measure false positives and false negatives, then tune the labels and threshold. The supplied classifier and initial policy are intended for English-language evaluation.

The model is pinned by both ID and immutable revision in [`.env.example`](.env.example). Changing either value requires rebuilding `topic-guard`:

```bash
docker compose build topic-guard
docker compose up -d topic-guard litellm open-webui
```

### Grounding and hallucination annotations

[`policies/grounding.yaml`](policies/grounding.yaml) controls the local, annotation-only grounding evaluator. OpenWebUI is configured with `RAG_SYSTEM_CONTEXT=true`, so retrieved `<source>` blocks arrive in a system message. The extractor accepts sources only from that trusted role; a user cannot create evidence by typing a fake `<source>` block in their prompt.

The evaluator uses the pinned English NLI model `cross-encoder/nli-MiniLM2-L6-H768`. It splits the answer into claims, divides retrieved text into bounded overlapping chunks, and measures whether each claim is entailed by at least one chunk. `evaluation.claim_support` decides when a claim counts as supported. `thresholds.grounded` and `thresholds.partial` determine the user-facing result for the overall supported-claim ratio.

Policy and limit changes are hot-reloaded from the mounted YAML file. They do not require a restart:

```yaml
evaluation:
  claim_support: 0.70

thresholds:
  grounded: 0.80
  partial: 0.50
```

Use a versioned evaluation set before changing these values. Generic NLI can produce false positives and false negatives, sentence splitting is approximate, and support by a retrieved document does not establish that the document is correct. This feature evaluates only responses with OpenWebUI RAG sources; it reports **Not evaluated** for ordinary chats.

The grounding model ID and immutable revision are configured in [`.env.example`](.env.example). Changing them requires rebuilding `topic-guard`. On the tested CPU deployment, the combined topic and grounding sidecar used about 670 MiB RAM; no second Ollama model or GPU is required for the evaluator.

### LiteLLM and TrendAI

[`litellm/config.yaml`](litellm/config.yaml) registers the local denied-topic guard in `pre_call` mode, the pinned TrendAI plugin in both `pre_call` and `post_call` modes, and the local grounding annotator in `post_call` mode. The TrendAI plugin reads its API key and endpoint from environment variables.

PII detection and redaction remain native TrendAI Guard capabilities. Configure the PII entities and actions in the Vision One AI Guard policy UI; this repository does not add Presidio or maintain a second PII policy.

For hosted Vision One, use the exact endpoint displayed in the LiteLLM integration page. Typical regional endpoints include:

```text
https://api.xdr.trendmicro.com/v3.0/aiSecurity
https://api.eu.xdr.trendmicro.com/v3.0/aiSecurity
```

Self-hosted AWS or Kubernetes deployments should use the Guard API endpoint supplied by that deployment.

### OpenWebUI tool-schema compatibility patch

Small local models can echo OpenWebUI built-in function schemas as ordinary text. The derived OpenWebUI image applies a narrow compatibility patch: when `ENABLE_PLUGINS=false`, built-in tools are not injected into plain chats.

The patch is intentionally fail-fast. If the targeted OpenWebUI source changes, the image build stops instead of silently producing a broken configuration. Review and update [`patches/apply_openwebui_builtin_tools_gate.py`](patches/apply_openwebui_builtin_tools_gate.py) before changing `OPEN_WEBUI_IMAGE`.

### Key rotation

OpenWebUI persists connection settings in its data volume. After rotating `LITELLM_MASTER_KEY`, update the LiteLLM connection key under **Admin Settings → Connections**, or start with a fresh `open-webui-data` volume. A stale persisted key can cause LiteLLM to return `No connected db` and hide the model list.

## Operations

```bash
# Stop services while preserving model and OpenWebUI data
docker compose down

# Restart after configuration changes
docker compose up -d --build

# Follow runtime logs
docker compose logs -f topic-guard litellm open-webui
```

Do not use `docker compose down -v` unless you intend to delete downloaded Ollama models and OpenWebUI application data.

## Production guidance

- Pin container images by immutable digest after validation.
- Validate topic-policy changes against a versioned test set before promotion.
- Validate grounding thresholds against supported, contradicted, mixed, and no-source RAG responses before promotion.
- Remove `--detailed_debug` from the LiteLLM command after initial troubleshooting; debug logs can contain prompts and responses.
- Keep `fallback_on_error: block` for fail-closed enforcement.
- Do not expose port `4000` publicly. It is published here for local testing and should be restricted or removed in production.
- Terminate TLS at a trusted reverse proxy and configure explicit CORS origins.
- Back up the OpenWebUI and Ollama volumes before upgrades.
- Review upstream release notes before updating OpenWebUI, LiteLLM, or the TrendAI submodule.

## Troubleshooting

### Topic checks return `503`

Check the sidecar health and logs:

```bash
docker compose ps topic-guard
docker compose logs topic-guard
```

An invalid `policies/topics.yaml`, a missing model, or a failed inference causes the policy to fail closed. Correct the problem and retry. The topic-guard service intentionally does not log raw prompt text.

### A topic is missed or over-blocked

Create representative positive and negative examples for the topic, then refine its `classifier_label` or adjust `threshold` in `policies/topics.yaml`. Avoid lowering the threshold based on one prompt because that can increase false positives across every topic. This classifier is an enforcement aid, not a deterministic substitute for policy testing.

### Grounding always says `Not evaluated`

Grounding runs only when OpenWebUI retrieval supplies `<source>` blocks in the system message. Confirm that the chat uses a document or Knowledge collection and that `RAG_SYSTEM_CONTEXT=true` remains set on `open-webui`. Ordinary chats intentionally report **Not evaluated**.

### Grounding says `Evaluation unavailable`

Check the shared sidecar and LiteLLM logs:

```bash
docker compose ps topic-guard litellm
docker compose logs topic-guard litellm
```

The answer remains visible because this diagnostic feature fails open. Correct an invalid `policies/grounding.yaml`, missing grounding model, sidecar connectivity problem, or inference error and retry.

### A grounding result looks wrong

Preserve the exact retrieved sources and answer as a regression case. Tune `evaluation.claim_support` only against a representative evaluation set. The checker measures textual entailment from retrieved content; it does not check source quality, current facts, completeness, bias, or whether retrieval selected the best document.

### `llama3.2` is missing

Verify LiteLLM can see it:

```bash
docker compose exec -T open-webui sh -lc \
  'curl -fsS -H "Authorization: Bearer $OPENAI_API_KEY" http://litellm:4000/v1/models'
```

If LiteLLM returns the model but OpenWebUI does not, check for a stale persisted LiteLLM key as described under **Key rotation**.

### Function JSON appears as the assistant response

Confirm the patched image was built and `ENABLE_PLUGINS=false` is present:

```bash
docker compose exec -T open-webui sh -lc \
  "grep -A6 'use_builtin_tools =' /app/backend/open_webui/utils/middleware.py"
```

Start a new chat after rebuilding; old malformed messages remain in conversation history.

### Build fails with `No space left on device`

Inspect reclaimable Docker storage:

```bash
docker system df
```

Review the output before pruning. Image and cache cleanup can remove layers needed by other local projects.

## Security and privacy

See [SECURITY.md](SECURITY.md). The latest user message, retrieved source excerpts, and model response are processed inside the local policy sidecar. Prompt and response content is also sent to the configured TrendAI Guard API for inspection. Confirm data handling, residency, and retention requirements for your environment before production use.

## Licensing

The integration files in this repository are licensed under Apache License 2.0; see [LICENSE](LICENSE).

Third-party components keep their own licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), the pinned plugin's [Apache 2.0 license](vendor/tm-v1-ai-guard-litellm-plugin/LICENSE), and the included [OpenWebUI license copy](LICENSES/Open-WebUI-License.txt).
