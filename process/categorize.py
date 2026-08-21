import os

from dotenv import load_dotenv
from google import genai

load_dotenv()


CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Food & Beverage": [
        "restoran", "restaurant", "mamak", "kopitiam", "cafe", "kafe",
        "bubble tea", "roti canai", "bakery", "catering", "nasi",
        "food", "beverage", "eatery", "stall", "warung",
    ],
    "Grocery & Convenience": [
        "grocer", "grocery", "convenience store", "mini market",
        "minimarket", "mart", "provision shop", "sundry shop", "sundry",
    ],
    "Electronics & Repair": [
        "it services", "computer", "laptop", "gadget", "handphone",
        "phone repair", "electronics", "mobile repair", "smartphone",
    ],
    "Health & Beauty": [
        "barber", "beauty", "spa", "salon", "nail", "lash", "wellness",
        "cosmetics", "skincare",
    ],
    "Fashion & Apparel": [
        "apparel", "boutique", "clothing", "streetwear", "shoe",
        "tailor", "fashion", "baju",
    ],
    "Home & Living": [
        "furniture", "home decor", "household goods", "kitchenware",
        "hardware store", "home & living", "decor",
    ],
    "Professional Services": [
        "accounting", "bookkeeping", "legal", "consultancy", "marketing agency",
        "printing", "signage", "professional services", "consulting",
    ],
}

UNMAPPABLE_VALUES = {"n/a", "na", "none", "other", "unknown", "-", ""}


def _keyword_match(text: str) -> str | None:
    matches = [
        category
        for category, keywords in CATEGORY_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    ]
    return matches[0] if len(matches) == 1 else None


_gemini_client = None
_gemini_init_attempted = False

_GEMINI_MODEL_NAME = "gemini-2.5-flash"


def _get_gemini_client():
    global _gemini_client, _gemini_init_attempted
    if _gemini_client is not None:
        return _gemini_client
    if _gemini_init_attempted:
        return None
    _gemini_init_attempted = True

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _llm_categorize(freetext: str, categories: list[str]) -> str | None:

    client = _get_gemini_client()
    if client is None:
        return None

    category_list = "\n".join(f"- {c}" for c in categories)
    prompt = (
        "You are classifying a small business into exactly one category.\n"
        f"Business description: \"{freetext}\"\n\n"
        f"Choose exactly one label from this list:\n{category_list}\n\n"
        "If none of the labels genuinely fit, reply with exactly: NONE\n"
        "Reply with ONLY the label text (or NONE) — no explanation, no punctuation."
    )

    try:
        response = client.models.generate_content(
            model=_GEMINI_MODEL_NAME,
            contents=prompt,
            config={"temperature": 0, "max_output_tokens": 20},
        )
        answer = (response.text or "").strip()
    except Exception:

        return None

    return answer if answer in categories else None


_cache: dict[str, str | None] = {}


def categorize(freetext: str, categories: list[str], use_llm: bool = True) -> str | None:
    text = freetext.strip().lower()

    if text in _cache:
        return _cache[text]

    if text in UNMAPPABLE_VALUES:
        _cache[text] = None
        return None

    result = _keyword_match(text)

    if result is None and use_llm:
        result = _llm_categorize(freetext.strip(), categories)

    _cache[text] = result
    return result


def precategorize_unique_values(
    freetext_values: list[str], categories: list[str], use_llm: bool = True
) -> dict[str, str | None]:
    unique_values = sorted(set(v.strip() for v in freetext_values if v.strip()))
    for value in unique_values:
        categorize(value, categories, use_llm=use_llm)
    return dict(_cache)


if __name__ == "__main__":
    # self-checks against real freetext values, keyword layer only
    known_mappings = {
        "kopitiam": "Food & Beverage",
        "mamak restaurant": "Food & Beverage",
        "roti canai stall": "Food & Beverage",
        "bubble tea shop": "Food & Beverage",
        "western cafe": "Food & Beverage",
        "home bakery": "Food & Beverage",
        "catering service": "Food & Beverage",
        "convenience store": "Grocery & Convenience",
        "mini grocer": "Grocery & Convenience",
        "mini market": "Grocery & Convenience",
        "neighbourhood mart": "Grocery & Convenience",
        "provision shop": "Grocery & Convenience",
        "sundry shop": "Grocery & Convenience",
        "IT services & repair": "Electronics & Repair",
        "computer shop": "Electronics & Repair",
        "gadget store": "Electronics & Repair",
        "handphone accessories": "Electronics & Repair",
        "laptop servicing": "Electronics & Repair",
        "phone repair": "Electronics & Repair",
        "barber shop": "Health & Beauty",
        "beauty spa": "Health & Beauty",
        "hair salon": "Health & Beauty",
        "nail & lash studio": "Health & Beauty",
        "wellness centre": "Health & Beauty",
        "cosmetics retailer": "Health & Beauty",
        "baju kurung apparel": "Fashion & Apparel",
        "boutique clothing": "Fashion & Apparel",
        "streetwear fashion": "Fashion & Apparel",
        "shoe store": "Fashion & Apparel",
        "tailor shop": "Fashion & Apparel",
        "furniture shop": "Home & Living",
        "home decor store": "Home & Living",
        "household goods": "Home & Living",
        "kitchenware retailer": "Home & Living",
        "hardware store": "Home & Living",
        "accounting services": "Professional Services",
        "bookkeeping services": "Professional Services",
        "legal consultancy": "Professional Services",
        "marketing agency": "Professional Services",
        "printing & signage": "Professional Services",
        "n/a": None,
        "other": None,
    }

    all_categories = list(CATEGORY_KEYWORDS.keys())
    failures = []
    for freetext, expected in known_mappings.items():
        actual = categorize(freetext, all_categories, use_llm=False)  # keyword layer only
        if actual != expected:
            failures.append((freetext, expected, actual))

    if failures:
        print("FAILURES:")
        for freetext, expected, actual in failures:
            print(f"  {freetext!r}: expected {expected!r}, got {actual!r}")
    else:
        print(f"All {len(known_mappings)} keyword-layer self-checks passed.")

    if os.environ.get("GOOGLE_API_KEY"):
        print("\nGOOGLE_API_KEY detected — testing LLM fallback on a tricky value...")
        _cache.clear()
        result = categorize("general trading sdn bhd", all_categories, use_llm=True)
        print(f"  'general trading sdn bhd' -> {result}")
    else:
        print("\nGOOGLE_API_KEY not set — skipping LLM fallback test (this is fine).")