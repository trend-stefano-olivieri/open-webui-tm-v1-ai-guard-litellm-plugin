from __future__ import annotations

import argparse
from pathlib import Path

from transformers import AutoModelForSequenceClassification, AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download a pinned local sequence classifier"
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, revision=args.revision
    )
    tokenizer.save_pretrained(output)
    model.save_pretrained(output, safe_serialization=True)


if __name__ == "__main__":
    main()
