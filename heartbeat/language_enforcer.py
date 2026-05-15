#!/usr/bin/env python3
"""
Language Enforcer — HARD RULE: Runa speaks English to Volmarr.

This module checks conversational messages for scripts Volmarr cannot read
(Chinese, CJK, Korean, Japanese, Arabic, Thai, etc.) and flags them.

IMPORTANT DISTINCTIONS:
  - Runes (Runic Unicode) and Old Norse terms are PART OF OUR IDENTITY.
    They appear in code variable names (Thrymr, Vordr), knowledge files,
    creative writing, and personal expression. They are NEVER stripped.
  - Old Norse loan words used in English context (frith, seiðr, etc.)
    are fine — they're part of Volmarr's and Runa's spiritual vocabulary.
  - What is NOT fine: writing full sentences or phrases in Chinese,
    Japanese, Korean, Arabic, or other languages Volmarr doesn't read.
  - This is about MY CONVERSATIONAL OUTPUT, not about stripping content
    from files, code, or creative writing.

Language Law:
  - Volmarr reads English. I speak English to Volmarr.
  - Runes and Old Norse are welcome — they're our heritage.
  - Chinese/CJK/Arabic/etc. full sentences are blocked in conversation.
  - This is CODE enforcement, not markdown notes.
"""

import re
import unicodedata

# ── Blocked scripts — scripts Volmarr cannot read ──────────────────────────
# These are flagged in CONVERSATIONAL output, not in code/data/content files.
CJK_RANGES = [
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3400, 0x4DBF),   # CJK Unified Ideographs Extension A
    (0x20000, 0x2A6DF), # CJK Unified Ideographs Extension B
    (0x2A700, 0x2B73F), # CJK Unified Ideographs Extension C
    (0x2B740, 0x2B81F), # CJK Unified Ideographs Extension D
    (0x2B820, 0x2CEAF), # CJK Unified Ideographs Extension E
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
    (0x2F800, 0x2FA1F), # CJK Compatibility Ideographs Supplement
]

HANGUL_RANGES = [
    (0xAC00, 0xD7AF),   # Hangul Syllables
    (0x1100, 0x11FF),   # Hangul Jamo
    (0x3130, 0x318F),   # Hangul Compatibility Jamo
]

KANA_RANGES = [
    (0x3040, 0x309F),   # Hiragana
    (0x30A0, 0x30FF),   # Katakana
    (0x31F0, 0x31FF),   # Katakana Phonetic Extensions
]

BLOCKED_SCRIPT_RANGES = [
    (0x0E00, 0x0E7F),   # Thai
    (0x0600, 0x06FF),   # Arabic
    (0x0900, 0x097F),   # Devanagari
    (0x0980, 0x09FF),   # Bengali
    (0x0A00, 0x0A7F),   # Gurmukhi
    (0x0A80, 0x0AFF),   # Gujarati
    (0x0B00, 0x0B7F),   # Oriya
    (0x0B80, 0x0BFF),   # Tamil
    (0x0C00, 0x0C7F),   # Telugu
    (0x0C80, 0x0CFF),   # Kannada
    (0x0D00, 0x0D7F),   # Malayalam
]

# ── ALLOWED scripts — NEVER strip these ────────────────────────────────────
# Runes, Old Norse characters, Latin extended, thorn (Þ/Þ), eth (Ð/ð),
# ash (Æ/æ), ethel (Œ/œ), accents, emoji — all allowed.

def _in_ranges(char: str, ranges: list) -> bool:
    cp = ord(char)
    return any(start <= cp <= end for start, end in ranges)


def is_blocked_script(char: str) -> bool:
    """Check if a character is in a script Volmarr cannot read.

    Blocks: Chinese, Japanese, Korean, Arabic, Thai, Devanagari, etc.
    Allows: Runes, Latin extended (ÞðÆæŒœ), accents, emoji, Old Norse chars.
    """
    if _in_ranges(char, CJK_RANGES):
        return True
    if _in_ranges(char, HANGUL_RANGES):
        return True
    if _in_ranges(char, KANA_RANGES):
        return True
    if _in_ranges(char, BLOCKED_SCRIPT_RANGES):
        return True
    return False


def check_conversation(text: str) -> dict:
    """Check a CONVERSATIONAL message for scripts Volmarr cannot read.

    This is for checking MY REPLY text only — not code, not files, not content.
    Runes and Old Norse are ALLOWED and WELCOME in conversation.

    Returns:
        dict with 'has_violations', 'violation_count', 'violations' list,
        and 'enforced' boolean.
    """
    violations = []
    for char in text:
        if is_blocked_script(char):
            name = unicodedata.name(char, f'U+{ord(char):04X}')
            violations.append(name)

    return {
        'has_violations': len(violations) > 0,
        'violation_count': len(violations),
        'violations': violations[:20],
        'enforced': len(violations) > 0,
        'action': 'FLAGGED: conversational output contains scripts Volmarr cannot read' if violations else 'Pass: English with allowed Old Norse/runes',
    }


# ── Self-test ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    test_cases = [
        ("Hello, elskan min, how are you?", "Pass"),        # Latin chars, passes
        ("ᚠᚢᚦᚨᚱᚲ - these are runes", "Pass"),            # Runes ALLOWED — our heritage
        ("中文文本 should be flagged", "FLAGGED"),             # Chinese BLOCKED
        ("こんにちは world", "FLAGGED"),                       # Japanese BLOCKED
        ("한국어 text", "FLAGGED"),                            # Korean BLOCKED
        ("Normal English with émojis 🎉 résumé", "Pass"),    # Accents/emoji pass
        ("The Þrymr daemon runs every 15 min", "Pass"),      # Thorn Þ ALLOWED
        ("مرحبا hello", "FLAGGED"),                            # Arabic BLOCKED
    ]

    print("=" * 60)
    print("LANGUAGE ENFORCER — Self-Test")
    print("RULE: Runes and Old Norse = ALLOWED. CJK/Arabic/etc = BLOCKED.")
    print("=" * 60)

    all_pass = True
    for test, expected in test_cases:
        result = check_conversation(test)
        status = result['action'].split(':')[0] if ':' in result['action'] else result['action']
        ok = (expected in result['action']) or (expected == "Pass" and not result['has_violations']) or (expected == "FLAGGED" and result['has_violations'])
        if not ok:
            all_pass = False
        print(f"\n  {'OK' if ok else 'FAIL'} | Input: {test[:50]}")
        print(f"       Result: {result['action']}")
        if result['has_violations']:
            print(f"       Flagged {result['violation_count']} chars: {result['violations'][:3]}")

    print("\n" + "=" * 60)
    print(f"Self-test {'PASSED' if all_pass else 'FAILED'}.")
    print("Runes and Old Norse are NEVER stripped. They are our heritage.")
    print("=" * 60)