#!/usr/bin/env python3
"""Shared utilities for zaihua-video pipeline scripts."""

import html
import os
import re
from pathlib import Path

# ─── Config ───
# Get project root (parent of scripts/ directory)
PROJECT_ROOT = Path(__file__).parent.parent
ROOT = PROJECT_ROOT / "dates"

# ─── Brand Patterns ───
BRAND_PATTERNS = [
    r"🌸\s*在花频道\s*[·・|｜-]?\s*备用频道\s*[·・|｜-]?\s*投稿通道",
    r"🌸\s*在花频道",
    r"🍀\s*在花频道",
    r"在花频道\s*[·・|｜-]?\s*备用频道\s*[·・|｜-]?\s*投稿通道",
    r"在花频道",
    r"备用频道",
    r"投稿通道",
    r"@?zaihuapd",
    r"@?zaihuatg",
    r"@?zaihuabot",
    r"@?zaihua",
    r"[·・|｜-]?\s*英文频道",
    r"[·・|｜-]?\s*茶馆讨论",
]


def clean_public_text(text):
    """Remove brand/channel promotion text from content."""
    text = html.unescape(str(text or ""))
    for pattern in BRAND_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ·・|｜-/，,。")
    return text


def is_internal_source_url(href):
    """Check if a URL points to internal/channel resources."""
    href = str(href or "").lower()
    return any(token in href for token in [
        "t.me/zaihua",
        "t.me/zaihuapd",
        "t.me/zaihuatg",
        "t.me/zaihuabot",
    ])


def load_env_file(path):
    """Load key=value pairs from a .env file into os.environ.
    
    Supports:
    - KEY=VALUE
    - KEY="VALUE WITH SPACES"
    - KEY='VALUE'
    - Comments starting with #
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        # Strip inline comments (only if not inside quotes)
        # Simple heuristic: find first unquoted #
        in_quotes = False
        quote_char = None
        comment_start = -1
        for i, ch in enumerate(line):
            if ch in '"\'':
                if not in_quotes:
                    in_quotes = True
                    quote_char = ch
                elif ch == quote_char:
                    in_quotes = False
            elif ch == '#' and not in_quotes:
                comment_start = i
                break
        if comment_start >= 0:
            line = line[:comment_start].rstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
