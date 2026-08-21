from __future__ import annotations

import argparse
import csv
import os
import sys
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()

_GEMINI_MODEL_NAME = "gemini-3.5-flash-lite"
_client = None

MIN_SECONDS_BETWEEN_REQUESTS = 15.0
_last_request_time: float | None = None


def _rate_limit() -> None:
    global _last_request_time
    if _last_request_time is not None:
        elapsed = time.monotonic() - _last_request_time
        wait = MIN_SECONDS_BETWEEN_REQUESTS - elapsed
        if wait > 0:
            time.sleep(wait)
    _last_request_time = time.monotonic()


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("error: GOOGLE_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    _client = genai.Client(api_key=api_key)
    return _client


_PROMPT_TEMPLATE = """You are sanity-checking merchant onboarding data.

Merchant name: "{name}"
Assigned business category: "{category}"

Does the merchant name plausibly match this category? Business names are
often in Malay/English/Chinese, so consider common naming conventions
(e.g. "Kedai" = shop, "Restoran" = restaurant, "Gerai" = stall).

Reply in EXACTLY this format, nothing else:
VERDICT: yes|no|unsure
REASON: <one short sentence, blank if VERDICT is yes>
"""

_cache: dict[tuple[str, str], tuple[str, str]] = {}


def check_mismatch(merchant_name: str, category: str) -> tuple[str, str]:
    key = (merchant_name.strip().lower(), category.strip().lower())
    if key in _cache:
        return _cache[key]

    client = _get_client()
    prompt = _PROMPT_TEMPLATE.format(name=merchant_name, category=category)

    _rate_limit()
    try:
        response = client.models.generate_content(
            model=_GEMINI_MODEL_NAME,
            contents=prompt,
            config={"temperature": 0, "max_output_tokens": 60},
        )
        text = (response.text or "").strip()
    except Exception as e:
        print(f"warning: LLM call failed for {merchant_name!r}: {e}", file=sys.stderr)
        result = ("unsure", "LLM call failed")
        _cache[key] = result
        return result

    verdict = "unsure"
    reason = ""
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("VERDICT:"):
            v = line.split(":", 1)[1].strip().lower()
            if v in ("yes", "no", "unsure"):
                verdict = v
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()

    result = (verdict, reason)
    _cache[key] = result
    return result


def run(input_path: str) -> None:
    with open(input_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    out_fieldnames = fieldnames + ["possible_category_mismatch"]

    total = len(rows)
    unique_pairs = len({
        (r["merchant_name"].strip().lower(), r["canonical_category"].strip().lower())
        for r in rows
    })
    print(
        f"Reviewing {total} rows ({unique_pairs} unique name/category pairs "
        f"-> at most {unique_pairs} real API calls, {MIN_SECONDS_BETWEEN_REQUESTS:.0f}s apart "
        f"-> up to ~{unique_pairs * MIN_SECONDS_BETWEEN_REQUESTS / 60:.1f} min)."
    )
    sys.stdout.flush()

    flagged_count = 0
    api_calls_made = 0
    for i, row in enumerate(rows, start=1):
        key = (row["merchant_name"].strip().lower(), row["canonical_category"].strip().lower())
        was_cached = key in _cache

        verdict, reason = check_mismatch(row["merchant_name"], row["canonical_category"])
        if verdict == "yes":
            row["possible_category_mismatch"] = ""
        else:
            row["possible_category_mismatch"] = reason or "Possible mismatch (unspecified reason)"
            flagged_count += 1

        if not was_cached:
            api_calls_made += 1

        tag = "cache" if was_cached else "api"
        print(
            f"[{i}/{total}] ({tag}) {row['merchant_name']!r} "
            f"-> {row['canonical_category']!r}: {verdict}"
        )
        sys.stdout.flush()

    with open(input_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nChecked {total} rows ({api_calls_made} real API calls), flagged {flagged_count} for review.")
    print(f"Updated {input_path} in place with 1 new column.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="output/clean.csv", help="clean.csv to update in place")
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=MIN_SECONDS_BETWEEN_REQUESTS,
        help="Minimum seconds between real API calls (default: 15)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    global MIN_SECONDS_BETWEEN_REQUESTS
    MIN_SECONDS_BETWEEN_REQUESTS = args.rate_limit
    run(args.input)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())