# Security policy

## Secrets

Never commit `.env`, Vision One tokens, LiteLLM keys, OpenWebUI secrets, exported application databases, or production logs. Use `.env.example` only as a template and store production credentials in a secrets manager.

If a credential is exposed, revoke or rotate it before removing it from Git history. Deleting a file in a later commit does not remove the secret from earlier commits.

## Prompt data and logging

The local policy sidecar processes the latest user message for topic enforcement and processes retrieved source excerpts plus model responses for grounding evaluation. It does not log raw prompt, source, or response content. Prompts and model responses are also sent to the configured TrendAI Guard API for inspection. Confirm organizational requirements for data residency, retention, and access before production use.

The denied-topic and TrendAI enforcement guardrails are configured to fail closed. If the local topic classifier, mounted topic policy, or TrendAI service is unavailable, LiteLLM rejects the request instead of sending unchecked content to the model. Grounding is diagnostic rather than enforcement: it fails open, preserves the answer, and adds an **Evaluation unavailable** annotation when possible.

Only source blocks extracted from system-role messages are trusted as grounding evidence. User-role `<source>` blocks are ignored. Keep `RAG_SYSTEM_CONTEXT=true` in OpenWebUI so retrieved context remains separate from user input.

LiteLLM's `--detailed_debug` mode is enabled for initial validation and can log prompt or response content. Remove it from `docker-compose.yaml` after troubleshooting.

## Policy changes

Treat `policies/topics.yaml` and `policies/grounding.yaml` as security-sensitive configuration. Require review, test changes against representative allowed and denied prompts plus supported and contradicted RAG answers, and retain the policies in version control. Topic and grounding classification are probabilistic and can produce false positives or false negatives.

## Reporting vulnerabilities

Do not open a public issue containing credentials, private prompts, customer data, or exploit details. Report vulnerabilities in upstream components through their respective security policies:

- [TrendAI LiteLLM Guardrail security policy](https://github.com/trendmicro/tm-v1-ai-guard-litellm-plugin/security/policy)
- [OpenWebUI security policy](https://github.com/open-webui/open-webui/security/policy)
- [LiteLLM security policy](https://github.com/BerriAI/litellm/security/policy)

For integration-specific concerns, use GitHub's private vulnerability reporting feature when enabled for this repository.
