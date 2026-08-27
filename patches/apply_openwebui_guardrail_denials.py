"""Render expected OpenWebUI guardrail denials as assistant messages.

OpenWebUI normally treats every upstream HTTP 400 as a failed chat. This
fail-fast source patch converts only known TrendAI and local topic-policy
denials into normal assistant responses; unrelated provider failures keep the
standard error path.
"""

from pathlib import Path
import sys


UNPATCHED = """            # When the upstream provider returns an error (e.g. HTTP 400
            # content-filter, quota exceeded), generate_chat_completion
            # returns a JSONResponse instead of raising.  Detect this and
            # raise so the except-block below emits chat:message:error +
            # chat:tasks:cancel, unblocking the frontend.
            if isinstance(response, JSONResponse) and response.status_code >= 400:
                try:
                    error_body = json.loads(response.body.decode('utf-8', 'replace'))
                    detail = error_body.get('error', error_body) if isinstance(error_body, dict) else error_body
                    if isinstance(detail, dict):
                        detail = detail.get('message', detail.get('detail', str(detail)))
                except Exception:
                    detail = f'Provider returned HTTP {response.status_code}'
                raise Exception(detail)
"""

PATCHED = """            # Guardrail denials are expected chat outcomes, not application
            # failures. Convert the known TrendAI and local topic-policy 400s
            # into an assistant response so the frontend shows the denial
            # instead of its generic \"Oops\" error. Other provider errors keep
            # the existing error path below.
            if isinstance(response, JSONResponse) and response.status_code >= 400:
                try:
                    error_body = json.loads(response.body.decode('utf-8', 'replace'))
                    detail = error_body.get('error', error_body) if isinstance(error_body, dict) else error_body
                    while isinstance(detail, dict):
                        nested_detail = next(
                            (detail[key] for key in ('message', 'detail', 'error') if key in detail),
                            None,
                        )
                        if nested_detail is None or nested_detail is detail:
                            break
                        detail = nested_detail
                except Exception:
                    detail = f'Provider returned HTTP {response.status_code}'

                guardrail_denial = (
                    response.status_code == status.HTTP_400_BAD_REQUEST
                    and isinstance(detail, str)
                    and detail.startswith(('Blocked by TrendAI Guard', 'Blocked by topic policy'))
                )
                if guardrail_denial:
                    denial_content = (
                        f'🛡️ {detail}\\n\\n'
                        '<!-- grounding-check -->\\n'
                        'ℹ️ Grounding: Not evaluated — the request was blocked before model generation.'
                    )
                    response = JSONResponse(
                        status_code=status.HTTP_200_OK,
                        content={
                            'id': f'guardrail-{uuid4()}',
                            'object': 'chat.completion',
                            'created': int(time.time()),
                            'model': form_data.get('model', ''),
                            'choices': [
                                {
                                    'index': 0,
                                    'message': {
                                        'role': 'assistant',
                                        'content': denial_content,
                                    },
                                    'finish_reason': 'content_filter',
                                }
                            ],
                        },
                    )
                else:
                    raise Exception(detail)
"""


def apply_patch(target: Path) -> None:
    content = target.read_text()

    if PATCHED in content:
        print(f"OpenWebUI guardrail-denial handling already present in {target}")
        return

    occurrences = content.count(UNPATCHED)
    if occurrences != 1:
        raise SystemExit(
            f"refusing to patch {target}: expected one target block, found {occurrences}"
        )

    target.write_text(content.replace(UNPATCHED, PATCHED, 1))
    print(f"Applied OpenWebUI guardrail-denial handling to {target}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply_openwebui_guardrail_denials.py <main.py>")

    apply_patch(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
