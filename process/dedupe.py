from collections import defaultdict


def _normalise_name_for_matching(name: str) -> str:
    return " ".join(name.strip().lower().split())


def deduplicate(clean_rows: list[dict]) -> list[dict]:
    # collapse dups by merchant name, keeping the row with the lowest submission_id

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in clean_rows:
        key = _normalise_name_for_matching(row["merchant_name"])
        groups[key].append(row)

    deduplicated: list[dict] = []
    for group in groups.values():
        winner = min(group, key=lambda r: r["submission_id"])
        winner = dict(winner)  # copy, don't mutate the original row
        winner["duplicates_collapsed"] = len(group)
        deduplicated.append(winner)

    return deduplicated


if __name__ == "__main__":
    # individual self-checks for deduplication logic
    sample_rows = [
        {"submission_id": "A010", "merchant_name": "gerai kasih", "contact_phone": "091"},
        {"submission_id": "A045", "merchant_name": "GERAI KASIH", "contact_phone": "092"},
        {"submission_id": "B001", "merchant_name": "Totally Different Biz", "contact_phone": "093"},
        {"submission_id": "A001", "merchant_name": "  Sejahtera Bahagia Trading ", "contact_phone": "094"},
        {"submission_id": "A013", "merchant_name": "sejahtera bahagia trading", "contact_phone": "095"},
    ]

    result = deduplicate(sample_rows)
    result_by_name = {r["merchant_name"]: r for r in result}

    assert len(result) == 3, f"expected 3 unique merchants, got {len(result)}"

    gerai = next(r for r in result if _normalise_name_for_matching(r["merchant_name"]) == "gerai kasih")
    assert gerai["submission_id"] == "A010", "expected lowest submission_id to win"
    assert gerai["duplicates_collapsed"] == 2

    sejahtera = next(
        r for r in result
        if _normalise_name_for_matching(r["merchant_name"]) == "sejahtera bahagia trading"
    )
    assert sejahtera["submission_id"] == "A001"
    assert sejahtera["duplicates_collapsed"] == 2

    different = next(r for r in result if r["merchant_name"] == "Totally Different Biz")
    assert different["duplicates_collapsed"] == 1

    print("All dedupe.py self-checks passed.")