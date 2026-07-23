def deduplicate_list(items):
    """
    Remove duplicates while preserving order.
    Comparison is case-insensitive.
    """

    if not items:
        return []

    seen = set()
    result = []

    for item in items:
        if not isinstance(item, str):
            continue

        cleaned = item.strip()

        if not cleaned:
            continue

        key = cleaned.lower()

        if key not in seen:
            seen.add(key)
            result.append(cleaned)

    return result