"""
Orb Arena - Utility Functions
Input sanitization and safe type conversion helpers.
"""

import math
import re

from constants import WORLD_WIDTH, WORLD_HEIGHT


def safe_float(value, default: float = 0.0) -> float:
    """Safely convert a value to a finite float, clamped to world bounds."""
    try:
        f = float(value)
        if not math.isfinite(f):
            return default
        # Clamp to reasonable world bounds to prevent absurd values
        return max(-1000, min(max(WORLD_WIDTH, WORLD_HEIGHT) + 1000, f))
    except (TypeError, ValueError):
        return default


def sanitize_name(raw: str) -> str:
    """Sanitize a player name: strip HTML/control chars, collapse whitespace, limit length."""
    # Strip HTML tags
    name = re.sub(r'<[^>]*>', '', raw)
    # Strip control characters and zero-width chars
    name = re.sub(r'[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufeff]', '', name)
    # Collapse whitespace
    name = ' '.join(name.split())
    # Limit length
    name = name[:15].strip()
    return name if name else "Anonymous"
