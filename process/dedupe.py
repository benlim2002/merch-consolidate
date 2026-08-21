from collections import defaultdict


def _normalise_name_for_matching(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _dedupe_key(row: dict) -> tuple[str, str]:
    name_key = _normalise_name_for_matching(row["merchant_name"]) # added region into the key to avoid merging same name in different regions, vice versa
    region_key = (row.get("region") or "").strip().lower()
    return (name_key, region_key)


def _winner_sort_key(row: dict) -> tuple[str, str]:
    return (row["registration_date"], row["submission_id"])


def deduplicate(clean_rows: list[dict]) -> list[dict]:
    # Collapse dups by (merchant name, region) — see _dedupe_key for why
    # region is part of the key. Keeps the row with the latest
    # registration_date — see _winner_sort_key.

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in clean_rows:
        groups[_dedupe_key(row)].append(row)

    deduplicated: list[dict] = []
    for group in groups.values():
        winner = max(group, key=_winner_sort_key)
        winner = dict(winner)  # copy, don't mutate the original row
        winner["duplicates_collapsed"] = len(group)
        deduplicated.append(winner)

    return deduplicated


if __name__ == "__main__":
    # individual self-checks for deduplication logic
    sample_rows = [
        {"submission_id": "A010", "merchant_name": "gerai kasih", "region": "Central", "contact_phone": "091", "registration_date": "2026-02-01"},
        {"submission_id": "A045", "merchant_name": "GERAI KASIH", "region": "central", "contact_phone": "092", "registration_date": "2026-04-15"},
        {"submission_id": "B001", "merchant_name": "Totally Different Biz", "region": "Southern", "contact_phone": "093", "registration_date": "2026-03-01"},
        {"submission_id": "A001", "merchant_name": "  Sejahtera Bahagia Trading ", "region": "Northern", "contact_phone": "094", "registration_date": "2026-05-20"},
        {"submission_id": "A013", "merchant_name": "sejahtera bahagia trading", "region": "Northern", "contact_phone": "095", "registration_date": "2026-01-10"},
        {"submission_id": "A020", "merchant_name": "Warung Impian Trading", "region": "Northern", "contact_phone": "096", "registration_date": "2026-01-01"},
        {"submission_id": "A021", "merchant_name": "warung impian trading", "region": "Sarawak", "contact_phone": "097", "registration_date": "2026-01-01"},
        {"submission_id": "C002", "merchant_name": "Tie Break Biz", "region": "East Coast", "contact_phone": "098", "registration_date": "2026-02-02"},
        {"submission_id": "C001", "merchant_name": "tie break biz", "region": "East Coast", "contact_phone": "099", "registration_date": "2026-02-02"},
    ]

    result = deduplicate(sample_rows)

    assert len(result) == 6, f"expected 6 unique (name, region) merchants, got {len(result)}"

    gerai = next(r for r in result if _normalise_name_for_matching(r["merchant_name"]) == "gerai kasih")
    assert gerai["submission_id"] == "A045", "expected latest registration_date to win"
    assert gerai["duplicates_collapsed"] == 2

    sejahtera = next(
        r for r in result
        if _normalise_name_for_matching(r["merchant_name"]) == "sejahtera bahagia trading"
    )
    assert sejahtera["submission_id"] == "A001", "expected latest registration_date to win"
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

    tie_break = next(r for r in result if _normalise_name_for_matching(r["merchant_name"]) == "tie break biz")
    assert tie_break["submission_id"] == "C002", "expected submission_id to break the date tie"
    assert tie_break["duplicates_collapsed"] == 2

    print("All dedupe.py self-checks passed.")