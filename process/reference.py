import sqlite3


class RegionInfo:
    def __init__(self, region: str, pic_name: str, pic_email: str):
        self.region = region
        self.pic_name = pic_name
        self.pic_email = pic_email

class ReferenceData:
    def __init__(self, categories: list[str], region_pic: dict[str, RegionInfo], existing_merchant_ids: set[str], existing_merchant_names: set[str]):
        self.categories = categories
        self.region_pic = region_pic
        self.existing_merchant_ids = existing_merchant_ids
        self.existing_merchant_names = existing_merchant_names

    def is_valid_region(self, region: str) -> bool:
        return region in self.region_pic

    def pic_email_for(self, region: str) -> str | None:
        info = self.region_pic.get(region)
        return info.pic_email if info else None

    def is_existing_merchant(self, merchant_id: str | None, merchant_name: str) -> bool:
        if merchant_id and merchant_id.strip():
            if merchant_id.strip() in self.existing_merchant_ids:
                return True
        normalised_name = _normalise_name_for_matching(merchant_name)
        return normalised_name in self.existing_merchant_names

def _normalise_name_for_matching(name: str) -> str:
    return " ".join(name.strip().lower().split())

def load_reference_data(db_path: str) -> ReferenceData:
    con = sqlite3.connect(db_path)
    try:
        con.row_factory = sqlite3.Row

        categories = [
            row["canonical_name"]
            for row in con.execute(
                "SELECT canonical_name FROM categories ORDER BY category_id"
            )
        ]

        region_pic = {
            row["region"]: RegionInfo(
                region=row["region"],
                pic_name=row["pic_name"],
                pic_email=row["pic_email"],
            )
            for row in con.execute(
                "SELECT region, pic_name, pic_email FROM region_pic"
            )
        }

        existing_rows = con.execute(
            "SELECT merchant_id, merchant_name FROM existing_merchants"
        ).fetchall()
        existing_merchant_ids = {row["merchant_id"] for row in existing_rows}
        existing_merchant_names = {
            _normalise_name_for_matching(row["merchant_name"]) for row in existing_rows
        }

        return ReferenceData(
            categories=categories,
            region_pic=region_pic,
            existing_merchant_ids=existing_merchant_ids,
            existing_merchant_names=existing_merchant_names,
        )
    finally:
        con.close()


if __name__ == "__main__":
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else "reference.db"
    ref = load_reference_data(db)
    print(f"Categories ({len(ref.categories)}): {ref.categories}")
    print(f"Existing merchants: {len(ref.existing_merchant_ids)}")
    print(f"Regions ({len(ref.region_pic)}):")
    
    for region, info in ref.region_pic.items():
        print(f"{region}: {info.pic_name}")