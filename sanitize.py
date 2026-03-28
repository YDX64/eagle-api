"""
Upstream veri sanitizasyonu - NowGoal/Goaloo'dan gelen verileri temizler.
Stored XSS riskini azaltır.
"""
import html
from typing import Any


def sanitize_text(text: Any) -> Any:
    """String'i HTML entity'lerden temizle."""
    if not isinstance(text, str):
        return text
    return html.escape(text)


def sanitize_dict(data: Any) -> Any:
    """Dict/list içindeki tüm string'leri recursive olarak sanitize et."""
    if isinstance(data, dict):
        return {k: sanitize_dict(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_dict(item) for item in data]
    elif isinstance(data, str):
        return sanitize_text(data)
    return data
