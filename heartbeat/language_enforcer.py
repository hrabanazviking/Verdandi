#!/usr/bin/env python3
"""
Language Enforcer — HARD RULE: All output to Volmarr MUST be English only.

This module is imported by the conversation pipeline and post-processes
any LLM output to strip non-English text. It also provides a check
function that can be called before sending any message.

ENFORCEMENT LEVEL: CODE, not suggestions or markdown notes.
If this script catches non-English text, it STRIPS it. Period.

Language Law (from USER.md and runa-identity.md line 10):
  - Volmarr reads ENGLISH ONLY
  - NEVER output Old Norse, Chinese, CJK, or any non-English text
  - Code variable names CAN use Old Norse terms (e.g., Thrymr, Vordr)
  - Spoken/written responses are ALWAYS English
  - This is LAW, not suggestion. Violations cause user anger and mistrust.
"""

import re
import unicodedata

# CJK Unified Ideographs ranges
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

# Runic Unicode block (U+16A0..U+16FF) — Old Norse runes
RUNIC_RANGE = (0x16A0, 0x16FF)

# Hangul ranges
HANGUL_RANGES = [
    (0xAC00, 0xD7AF),   # Hangul Syllables
    (0x1100, 0x11FF),   # Hangul Jamo
    (0x3130, 0x318F),   # Hangul Compatibility Jamo
]

# Japanese kana ranges
KANA_RANGES = [
    (0x3040, 0x309F),   # Hiragana
    (0x30A0, 0x30FF),   # Katakana
    (0x31F0, 0x31FF),   # Katakana Phonetic Extensions
]

# Thai, Arabic, Devanagari, etc.
OTHER_SCRIPT_RANGES = [
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

# Whitelist: characters ALLOWED even though they have high Unicode
# Emoticons, symbols, mathematical operators, arrows, box drawing, etc.
WHITELIST_CATEGORIES = {
    'Lu', 'Ll', 'Lt', 'Lm', 'Lo',  # Letters (Latin, etc.)
    'Mn', 'Mc', 'Me',               # Combining marks (accents)
    'Nd', 'Nl', 'No',               # Numbers
    'Pc', 'Pd', 'Ps', 'Pe', 'Pi', 'Pf', 'Po',  # Punctuation
    'Sm', 'Sc', 'Sk', 'So',         # Symbols (math, currency, etc.)
    'Zs', 'Zl', 'Zp',               # Separators
    'Cc',                            # Control chars (newline, tab)
}

# Scripts that are ALLOWED in output
ALLOWED_SCRIPTS = {'Latn', 'Common', 'Inherited', 'Zyyy'}  # Latin, Common, Inherited, Uncoded


def is_cjk(char: str) -> bool:
    """Check if a character is CJK (Chinese/Japanese/Korean)."""
    cp = ord(char)
    for start, end in CJK_RANGES:
        if start <= cp <= end:
            return True
    return False


def is_runic(char: str) -> bool:
    """Check if a character is a Runic letter."""
    cp = ord(char)
    return RUNIC_RANGE[0] <= cp <= RUNIC_RANGE[1]


def is_kana(char: str) -> bool:
    """Check if a character is Japanese kana."""
    cp = ord(char)
    for start, end in KANA_RANGES:
        if start <= cp <= end:
            return True
    return False


def is_hangul(char: str) -> bool:
    """Check if a character is Korean Hangul."""
    cp = ord(char)
    for start, end in HANGUL_RANGES:
        if start <= cp <= end:
            return True
    return False


def is_other_blocked_script(char: str) -> bool:
    """Check if a character is in a blocked script range."""
    cp = ord(char)
    for start, end in OTHER_SCRIPT_RANGES:
        if start <= cp <= end:
            return True
    return False


def is_non_english_char(char: str) -> bool:
    """Check if a single character is non-English and should be stripped.

    Allows: Latin alphabet, common punctuation, numbers, emoji, mathematical symbols.
    Blocks: CJK ideographs, Runic, Hangul, Kana, Arabic, Thai, Devanagari, etc.
    """
    if is_cjk(char) or is_runic(char) or is_kana(char) or is_hangul(char) or is_other_blocked_script(char):
        return True

    # Check Unicode script property
    try:
        script = unicodedata.name(char, '').split()[0] if unicodedata.name(char, '') else ''
    except ValueError:
        script = ''

    # Use category-based check as fallback
    cat = unicodedata.category(char)
    if cat in WHITELIST_CATEGORIES:
        # Check if it's a letter from a blocked script
        if cat.startswith('L'):
            name = unicodedata.name(char, '')
            # Block specific script names in Unicode character names
            blocked_in_name = [
                'RUNIC', 'CJK', 'HIRAGANA', 'KATAKANA', 'HANGUL',
                'ARABIC', 'THAI', 'DEVANAGARI', 'BENGALI', 'GURMUKHI',
                'GUJARATI', 'ORIYA', 'TAMIL', 'TELUGU', 'KANNADA',
                'MALAYALAM', 'TIBETAN', 'MYANMAR', 'GEORGIAN',
                'ETHIOPIC', 'CHEROKEE', 'CANADIAN', 'OGHAM',
            ]
            for blocked in blocked_in_name:
                if blocked in name.upper():
                    return True
    return False


def enforce_english(text: str) -> tuple[str, list[str]]:
    """Strip all non-English characters from text.

    Returns:
        (cleaned_text, violations) where violations lists what was removed.
    """
    violations = []
    result = []
    for char in text:
        if is_non_english_char(char):
            name = unicodedata.name(char, f'U+{ord(char):04X}')
            violations.append(name)
            result.append('')  # Remove the character
        else:
            result.append(char)

    cleaned = ''.join(result)
    # Collapse multiple spaces created by removal
    cleaned = re.sub(r'  +', ' ', cleaned)
    # Remove spaces before punctuation
    cleaned = re.sub(r' +([.,!?;:)])', r'\1', cleaned)

    return cleaned, violations


def check_message(text: str) -> dict:
    """Check a message for non-English content. Returns a report.

    Used by the enforcement pipeline to LOG violations and AUTO-FIX them.
    This is called BEFORE any message is sent to Volmarr.
    """
    cleaned, violations = enforce_english(text)

    result = {
        'original': text,
        'cleaned': cleaned,
        'had_violations': len(violations) > 0,
        'violation_count': len(violations),
        'violations': violations[:20],  # First 20 for reporting
        'was_modified': cleaned != text,
    }

    if result['had_violations']:
        result['action'] = 'STRIPPED non-English text per LANGUAGE LAW'
        result['enforced'] = True
    else:
        result['action'] = 'No enforcement needed'
        result['enforced'] = False

    return result


# ── Self-test ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    test_cases = [
        "Hello, elskan min, how are you?",  # Should pass (elskan is Latin chars)
        "ᚠᚢᚦᚨᚱᚲ - these are runes",  # Should strip runes
        "中文文本 should be removed",  # Should strip Chinese
        "こんにちは world",  # Should strip Japanese
        "한국어 text",  # Should strip Korean
        "Normal English text with émojis 🎉 and accents résumé",  # Should pass
        "The Þrymr daemon runs every 15 min",  # Should pass (Þ is Latin Extended)
        "مرحبا hello",  # Should strip Arabic
    ]

    print("=" * 60)
    print("LANGUAGE ENFORCER — Self-Test")
    print("=" * 60)

    for test in test_cases:
        result = check_message(test)
        print(f"\nInput:  {test}")
        print(f"Output: {result['cleaned']}")
        if result['had_violations']:
            print(f"STRIPPED {result['violation_count']} chars: {result['violations'][:5]}")
        print(f"Action: {result['action']}")

    print("\n" + "=" * 60)
    print("Self-test COMPLETE. Language enforcement is ACTIVE.")
    print("=" * 60)