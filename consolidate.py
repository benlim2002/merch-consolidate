from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
from dataclasses import dataclass, field

from process.categorize import categorize, precategorize_unique_values
from process.dedupe import deduplicate
from process.reference import ReferenceData, load_reference_data
from process.validate import (
    format_date_iso,
    normalise_date,
    normalise_email,
    normalise_name,
    normalise_phone,
    resolve_region_alias,
    validate_submission,
)

CLEAN_FIELDNAMES = [
    "merchant_name",
    "canonical_category",
    "region",
    "contact_phone",
    "contact_email",
    "registration_date",
    "region_pic_email",
    "source_submission_id",
    "duplicates_collapsed",
]

ERROR_FIELDNAMES = [
    "submission_id",
    "source_file",
    "merchant_name",
    "region",
    "region_pic_email",
    "rejection_reasons",
]


@dataclass
class Stats:
# summary run
    files_read: int = 0
    rows_read: int = 0
    regions_aliased: int = 0
    rows_rejected: int = 0
    rows_passed_validation: int = 0
    unique_merchants_written: int = 0
    duplicates_collapsed: int = 0
    unique_freetext_values: int = 0
    rejection_reason_counts: dict = field(default_factory=dict)

    def record_reasons(self, reasons: list[str]) -> None:
        for reason in reasons:
            # bucket by the fixed prefix so "Invalid region: 'Penang'" and
            # "Invalid region: 'KL'" count under one bucket, not two.
            bucket = reason.split(":")[0].split(" '")[0]
            self.rejection_reason_counts[bucket] = (
                self.rejection_reason_counts.get(bucket, 0) + 1
            )

    def print_summary(self) -> None:
        print("\n--- consolidate.py summary ---")
        print(f"Files read:              {self.files_read}")
        print(f"Rows read:               {self.rows_read}")
        print(f"Regions aliased:         {self.regions_aliased}")
        print(f"Rows rejected:           {self.rows_rejected}")
        print(f"Rows passed validation:  {self.rows_passed_validation}")
        print(f"  -> unique merchants:   {self.unique_merchants_written}")
        print(f"  -> duplicates merged:  {self.duplicates_collapsed}")
        print(f"Unique freetext values:  {self.unique_freetext_values}")
        if self.rejection_reason_counts:
            print("Rejection reasons:")
            for reason, count in sorted(
                self.rejection_reason_counts.items(), key=lambda kv: -kv[1]
            ):
                print(f"  {count:>4}  {reason}")


def find_partner_files(data_dir: str) -> list[str]:
    pattern = os.path.join(data_dir, "submissions_partner*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No files matching 'submissions_partner*.csv' found in '{data_dir}'."
        )
    return files


def read_partner_rows(files: list[str]) -> tuple[list[dict], int]:
    rows: list[dict] = []
    regions_aliased = 0
    for path in files:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not any((v or "").strip() for v in row.values()):
                    continue
                row["source_file"] = os.path.basename(path)
                original_region = row.get("region", "")
                if original_region:
                    resolved_region = resolve_region_alias(original_region)
                    if resolved_region != original_region.strip():
                        regions_aliased += 1
                    row["region"] = resolved_region
                rows.append(row)
    return rows, regions_aliased


def resolve_category(row: dict, categories: list[str], use_llm: bool) -> str | None:
    freetext = (row.get("business_category_freetext") or "").strip()
    if not freetext:
        return None
    return categorize(freetext, categories, use_llm=use_llm)


def build_clean_row(
    row: dict, canonical_category: str, reference: ReferenceData
) -> dict:
    """Normalise a row that has already passed every validation rule."""
    region = row["region"].strip()
    parsed_date = normalise_date(row["registration_date"])
    return {
        "submission_id": row["submission_id"].strip(),
        "merchant_name": normalise_name(row["merchant_name"]),
        "canonical_category": canonical_category,
        "region": region,
        "contact_phone": normalise_phone(row["contact_phone"]),
        "contact_email": normalise_email(row["contact_email"]),
        "registration_date": format_date_iso(parsed_date),
        "region_pic_email": reference.pic_email_for(region) or "",
    }


def build_error_row(row: dict, reasons: list[str], reference: ReferenceData) -> dict:
# blawnk pic if region invalid
    region = (row.get("region") or "").strip()
    return {
        "submission_id": row.get("submission_id", "").strip(),
        "source_file": row.get("source_file", ""),
        "merchant_name": (row.get("merchant_name") or "").strip(),
        "region": region,
        "region_pic_email": reference.pic_email_for(region) or "",
        "rejection_reasons": "; ".join(reasons),
    }


def write_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run(data_dir: str, db_path: str, out_dir: str, use_llm: bool) -> Stats:
    stats = Stats()

    reference = load_reference_data(db_path)

    files = find_partner_files(data_dir)
    stats.files_read = len(files)

    rows, regions_aliased = read_partner_rows(files)
    stats.rows_read = len(rows)
    stats.regions_aliased = regions_aliased


    freetext_values = [row.get("business_category_freetext", "") for row in rows]
    precategorize_unique_values(freetext_values, reference.categories, use_llm=use_llm)
    stats.unique_freetext_values = len(
        {v.strip() for v in freetext_values if v.strip()}
    )

    clean_rows: list[dict] = []
    error_rows: list[dict] = []

    for row in rows:
        canonical_category = resolve_category(row, reference.categories, use_llm)
        reasons = validate_submission(row, reference, canonical_category)

        if reasons:
            stats.rows_rejected += 1
            stats.record_reasons(reasons)
            error_rows.append(build_error_row(row, reasons, reference))
            continue

        stats.rows_passed_validation += 1
        clean_rows.append(build_clean_row(row, canonical_category, reference))

    deduplicated = deduplicate(clean_rows)
    stats.unique_merchants_written = len(deduplicated)
    stats.duplicates_collapsed = sum(
        r.get("duplicates_collapsed", 1) - 1 for r in deduplicated
    )

    clean_output = [
        {
            "merchant_name": r["merchant_name"],
            "canonical_category": r["canonical_category"],
            "region": r["region"],
            "contact_phone": r["contact_phone"],
            "contact_email": r["contact_email"],
            "registration_date": r["registration_date"],
            "region_pic_email": r["region_pic_email"],
            "source_submission_id": r["submission_id"],
            "duplicates_collapsed": r.get("duplicates_collapsed", 1),
        }
        for r in deduplicated
    ]
    # Deterministic ordering makes diffs between runs meaningful.
    clean_output.sort(key=lambda r: r["source_submission_id"])
    error_rows.sort(key=lambda r: r["submission_id"])

    os.makedirs(out_dir, exist_ok=True)
    write_csv(os.path.join(out_dir, "clean.csv"), CLEAN_FIELDNAMES, clean_output)
    write_csv(os.path.join(out_dir, "errors.csv"), ERROR_FIELDNAMES, error_rows)

    return stats


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", default="data", help="Directory containing submissions_partner*.csv"
    )
    parser.add_argument("--db", default="reference.db", help="Path to reference.db")
    parser.add_argument(
        "--out-dir", default="output", help="Directory to write clean.csv / errors.csv into"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip the LLM fallback for category classification (keyword layer only)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        stats = run(
            data_dir=args.data_dir,
            db_path=args.db,
            out_dir=args.out_dir,
            use_llm=not args.no_llm,
        )
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    stats.print_summary()
    print(f"\nWrote {os.path.join(args.out_dir, 'clean.csv')}")
    print(f"Wrote {os.path.join(args.out_dir, 'errors.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())