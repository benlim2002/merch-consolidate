import re
from datetime import date, datetime
from process.reference import ReferenceData

REFERENCE_DATE = date(2026, 6, 1)


# normalization helpers
def normalise_name(name: str) -> str:
    collapsed = " ".join(name.strip().split())
    return collapsed.title()


def normalise_email(email: str) -> str:
    return email.strip().lower()


REGION_ALIASES: dict[str, str] = {
    "kl": "Central",
    "klang valley": "Central",
    "penang": "Northern",
}


def resolve_region_alias(region: str) -> str:
    trimmed = region.strip()
    key = " ".join(trimmed.lower().split())
    return REGION_ALIASES.get(key, trimmed)


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_plausible_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email.strip()))


def normalise_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("60") and len(digits) > 2:
        digits = "0" + digits[2:]
    return digits


def is_valid_phone(normalised_phone: str) -> bool:
    return len(normalised_phone) >= 9


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")


def normalise_date(raw_date: str) -> date | None:

# parses both YYYY-MM-DD or D/M/YYYY 
    raw_date = raw_date.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw_date, fmt).date()
        except ValueError:
            continue
    return None


def format_date_iso(parsed_date: date) -> str:
    return parsed_date.strftime("%Y-%m-%d")

#business rules
REQUIRED_FIELDS = [
    "merchant_name",
    "region",
    "contact_phone",
    "contact_email",
    "registration_date",
    "business_category_freetext",
]


def validate_submission(
    row: dict,
    reference: ReferenceData,
    canonical_category: str | None,
) -> list[str]:

    reasons: list[str] = []

    # Rule 1: required fields
    missing = [f for f in REQUIRED_FIELDS if not row.get(f, "").strip()]
    if missing:
        reasons.append(f"Missing required field(s): {', '.join(missing)}")

    # Rule 2: valid region
    region = row.get("region", "").strip()
    if region and not reference.is_valid_region(region):
        reasons.append(f"Invalid region: '{region}'")

    # Rule 3: valid email
    email = row.get("contact_email", "").strip()
    if email and not is_plausible_email(email):
        reasons.append(f"Invalid email format: '{email}'")

    # Rule 4: valid phone
    phone = row.get("contact_phone", "").strip()
    if phone:
        normalised_phone = normalise_phone(phone)
        if not is_valid_phone(normalised_phone):
            reasons.append(
                f"Phone has fewer than 9 digits after normalising: '{phone}'"
            )

    # Rule 5: mappable category
    freetext = row.get("business_category_freetext", "").strip()
    if freetext and canonical_category is None:
        reasons.append(
            f"Could not map business category '{freetext}' to any canonical category"
        )

    # Rule 6: sane date
    raw_date = row.get("registration_date", "").strip()
    if raw_date:
        parsed = normalise_date(raw_date)
        if parsed is None:
            reasons.append(f"Unparseable registration date: '{raw_date}'")
        elif parsed > REFERENCE_DATE:
            reasons.append(
                f"Registration date '{raw_date}' is after reference date {REFERENCE_DATE.isoformat()}"
            )

    # Rule 7: not already onboarded
    merchant_name = row.get("merchant_name", "").strip()
    existing_id = row.get("existing_merchant_id", "").strip()
    if merchant_name and reference.is_existing_merchant(existing_id, merchant_name):
        reasons.append("Merchant already onboarded (matched by id or name)")

    return reasons


if __name__ == "__main__":
    assert normalise_phone("+60-12-3456789") == "0123456789"
    assert normalise_phone("012-3456789") == "0123456789"
    assert normalise_phone("03-1122") == "031122"
    assert not is_valid_phone(normalise_phone("03-1122"))
    assert is_plausible_email("foo@bar.com")
    assert not is_plausible_email("not-an-email")
    assert normalise_date("2026-01-18") == date(2026, 1, 18)
    assert normalise_date("21/03/2026") == date(2026, 3, 21)
    assert normalise_date("not-a-date") is None
    assert normalise_name("  gerai   emas & sons ") == "Gerai Emas & Sons"
    print("All validate.py self-checks passed.")