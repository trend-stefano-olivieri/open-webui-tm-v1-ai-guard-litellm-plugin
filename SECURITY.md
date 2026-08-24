# Security policy

## Secrets

Never commit `.env`, Vision One tokens, LiteLLM keys, OpenWebUI secrets, exported application databases, or production logs. Use `.env.example` only as a template and store production credentials in a secrets manager.

If a credential is exposed, revoke or rotate it before removing it from Git history. Deleting a file in a later commit does not remove the secret from earlier commits.

## Prompt data and logging

The denied-topic sidecar processes the latest user message locally and does not log raw prompt content. Prompts and model responses are also sent to the configured TrendAI Guard API for inspection. Confirm organizational requirements for data residency, retention, and access before production use.

Both guardrails are configured to fail closed. If the local classifier, mounted topic policy, or TrendAI service is unavailable, LiteLLM rejects the request instead of sending unchecked content to the model.

LiteLLM's `--detailed_debug` mode is enabled for initial validation and can log prompt or response content. Remove it from `docker-compose.yaml` after troubleshooting.

## Policy changes

Treat `policies/topics.yaml` as security-sensitive configuration. Require review, test topic changes against representative allowed and denied prompts, and retain the policy in version control. Topic classification is probabilistic and can produce false positives or false negatives.

## Reporting vulnerabilities

Do not open a public issue containing credentials, private prompts, customer data, or exploit details. Report vulnerabilities in upstream components through their respective security policies:

- [TrendAI LiteLLM Guardrail security policy](https://github.com/trendmicro/tm-v1-ai-guard-litellm-plugin/security/policy)
- [OpenWebUI security policy](https://github.com/open-webui/open-webui/security/policy)
- [LiteLLM security policy](https://github.com/BerriAI/litellm/security/policy)

For integration-specific concerns, use GitHub's private vulnerability reporting feature when enabled for this repository.
