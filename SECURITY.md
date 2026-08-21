# Security policy

## Secrets

Never commit `.env`, Vision One tokens, LiteLLM keys, OpenWebUI secrets, exported application databases, or production logs. Use `.env.example` only as a template and store production credentials in a secrets manager.

If a credential is exposed, revoke or rotate it before removing it from Git history. Deleting a file in a later commit does not remove the secret from earlier commits.

## Prompt data and logging

Prompts and model responses are sent to the configured TrendAI Guard API for inspection. Confirm organizational requirements for data residency, retention, and access before production use.

LiteLLM's `--detailed_debug` mode is enabled for initial validation and can log prompt or response content. Remove it from `docker-compose.yaml` after troubleshooting.

## Reporting vulnerabilities

Do not open a public issue containing credentials, private prompts, customer data, or exploit details. Report vulnerabilities in upstream components through their respective security policies:

- [TrendAI LiteLLM Guardrail security policy](https://github.com/trendmicro/tm-v1-ai-guard-litellm-plugin/security/policy)
- [OpenWebUI security policy](https://github.com/open-webui/open-webui/security/policy)
- [LiteLLM security policy](https://github.com/BerriAI/litellm/security/policy)

For integration-specific concerns, use GitHub's private vulnerability reporting feature when enabled for this repository.
