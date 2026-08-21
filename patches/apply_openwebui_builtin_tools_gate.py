"""Apply the OpenWebUI built-in-tool compatibility gate.

This patch prevents small plain-chat models from receiving built-in function
schemas when OpenWebUI plugins are disabled. It fails closed when the expected
upstream source shape changes.
"""

from pathlib import Path
import sys


UNPATCHED = """    ) or (
        bool(metadata.get('session_id'))
        and metadata.get('params', {}).get('function_calling') != 'legacy'
"""

PATCHED = """    ) or (
        ENABLE_PLUGINS
        and bool(metadata.get('session_id'))
        and metadata.get('params', {}).get('function_calling') != 'legacy'
"""


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply_openwebui_builtin_tools_gate.py <middleware.py>")

    target = Path(sys.argv[1])
    content = target.read_text()

    if PATCHED in content:
        print(f"OpenWebUI built-in-tool gate already present in {target}")
        return

    occurrences = content.count(UNPATCHED)
    if occurrences != 1:
        raise SystemExit(
            f"refusing to patch {target}: expected one target block, found {occurrences}"
        )

    target.write_text(content.replace(UNPATCHED, PATCHED, 1))
    print(f"Applied OpenWebUI built-in-tool gate to {target}")


if __name__ == "__main__":
    main()
