from collections import defaultdict


def _normalise_name_for_matching(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _dedupe_key(row: dict) -> tuple[str, str]:
    name_key = _normalise_name_for_matching(row["merchant_name"]) # added region into the key to avoid merging same name in different regions, vice versa
    region_key = (row.get("region") or "").strip().lower()
    return (name_key, region_key)


def deduplicate(clean_rows: list[dict]) -> list[dict]:
    # collapse dups by (merchant name, region), keeping the row with the lowest
    # submission_id — see _dedupe_key for why region is part of the key.

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in clean_rows:
        groups[_dedupe_key(row)].append(row)

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
        {"submission_id": "A010", "merchant_name": "gerai kasih", "region": "Central", "contact_phone": "091"},
        {"submission_id": "A045", "merchant_name": "GERAI KASIH", "region": "central", "contact_phone": "092"},
        {"submission_id": "B001", "merchant_name": "Totally Different Biz", "region": "Southern", "contact_phone": "093"},
        {"submission_id": "A001", "merchant_name": "  Sejahtera Bahagia Trading ", "region": "Northern", "contact_phone": "094"},
        {"submission_id": "A013", "merchant_name": "sejahtera bahagia trading", "region": "Northern", "contact_phone": "095"},
        {"submission_id": "A020", "merchant_name": "Warung Impian Trading", "region": "Northern", "contact_phone": "096"},
        {"submission_id": "A021", "merchant_name": "warung impian trading", "region": "Sarawak", "contact_phone": "097"},
    ]

    result = deduplicate(sample_rows)

    assert len(result) == 5, f"expected 5 unique (name, region) merchants, got {len(result)}"

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

    warung_rows = [
        r for r in result
        if _normalise_name_for_matching(r["merchant_name"]) == "warung impian trading"
    ]
    assert len(warung_rows) == 2, "same name in different regions must stay separate"
    assert {r["region"] for r in warung_rows} == {"Northern", "Sarawak"}
    assert all(r["duplicates_collapsed"] == 1 for r in warung_rows)

    print("All dedupe.py self-checks passed.")