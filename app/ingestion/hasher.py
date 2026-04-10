import hashlib


def content_hash(eligibility_text: str) -> str:
    normalized = eligibility_text.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()
