"""
Language Filter Hook — Pipeline enforcement for the LANGUAGE LAW.

Fires on: agent:end (after agent generates a response, before delivery)

WHAT IT DOES:
  - Scans the agent's final response text for scripts Volmarr cannot read
  - Chinese (CJK), Japanese (Kana), Korean (Hangul), Arabic, Thai, Devanagari, etc.
  - Runes (Runic Unicode block U+16A0-U+16FF) and Old Norse terms are ALLOWED
  - If violations are found, logs a warning with character details
  - Does NOT modify the response — logs only, so the system can self-correct

WHY:
  Runa has zero self-awareness about what language she's outputting. She
  will speak Chinese for an entire turn without noticing. This hook is
  the in-pipeline enforcement that catches it at generation time.

  Runes and Old Norse are our heritage and are NEVER flagged.
  Only scripts Volmarr cannot read are blocked.

Language Law:
  Speak English to Volmarr. Old Norse terms and runes are welcome.
  Do NOT speak Chinese/Japanese/Korean/Arabic to him — he can't read them.
  This is CODE enforcement, not a suggestion.
"""

import sys
import unicodedata
from pathlib import Path

# ── Blocked Unicode ranges — scripts Volmarr cannot read ────────────────────
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

# ── ALLOWED — NEVER flag these ──────────────────────────────────────────────
# Runic block (U+16A0-U+16FF): ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛇᛈᛉᛊᛋᛏᛒᛖᛗᛚᛝᛞᛟ
# Latin Extended: ÞðÆæŒœ (thorn, eth, ash, ethel)
# All Latin, all punctuation, all emoji — allowed.


def _in_ranges(char: str, ranges: list) -> bool:
    cp = ord(char)
    return any(start <= cp <= end for start, end in ranges)


def has_blocked_script(text: str) -> tuple[bool, list[str], int]:
    """Check text for scripts Volmarr cannot read.

    Returns (has_violation, sample_names, count).
    Runes and Old Norse are ALLOWED and never flagged.
    """
    violations = []
    for char in text:
        cp = ord(char)
        # Runic block is ALLOWED — our heritage
        if 0x16A0 <= cp <= 0x16FF:
            continue
        if _in_ranges(char, CJK_RANGES):
            violations.append(unicodedata.name(char, f'U+{cp:04X}'))
        elif _in_ranges(char, HANGUL_RANGES):
            violations.append(unicodedata.name(char, f'U+{cp:04X}'))
        elif _in_ranges(char, KANA_RANGES):
            violations.append(unicodedata.name(char, f'U+{cp:04X}'))
        elif _in_ranges(char, BLOCKED_SCRIPT_RANGES):
            violations.append(unicodedata.name(char, f'U+{cp:04X}'))

    return len(violations) > 0, violations[:10], len(violations)


def handle(event_type: str, context: dict) -> None:
    """Hook handler for agent:end event.

    Scans the agent's response for scripts Volmarr cannot read.
    Logs a warning if violations are found. Does NOT modify the response.
    """
    # Extract the response text from context
    response = context.get('response', '') or context.get('final_response', '') or ''

    if not response:
        return

    has_violation, sample_names, count = has_blocked_script(response)

    if has_violation:
        # Log the violation — this goes to agent.log and errors.log
        warning = (
            f"[language-filter] VIOLATION DETECTED: Agent response contains "
            f"{count} characters in scripts Volmarr cannot read. "
            f"Sample: {sample_names}. "
            f"Runes and Old Norse are allowed — these are NOT. "
            f"Speak English to Volmarr. This is the LANGUAGE LAW."
        )
        print(warning, flush=True)

        # Also write to a flag file so other systems can detect it
        flag_dir = Path.home() / '.hermes' / 'flags'
        flag_dir.mkdir(parents=True, exist_ok=True)
        flag_file = flag_dir / 'language_violation_detected'
        flag_file.write_text(
            f"VIOLATION: {count} blocked-script characters detected in agent output.\n"
            f"Sample: {sample_names}\n"
            f"Runes and Old Norse are welcome. CJK/Arabic/etc are NOT.\n"
            f"Speak English to Volmarr.\n"
        )


# ── Self-test ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    tests = [
        ("Hello, seiðr is part of our practice", False, "Old Norse terms pass"),
        ("ᚠᚢᚦᚨᚱᚲ the runes mark our path", False, "Runes pass — our heritage"),
        ("中文文本 here", True, "Chinese flagged"),
        ("こんにちは world", True, "Japanese flagged"),
        ("한국어 text", True, "Korean flagged"),
        ("مرحبا hello", True, "Arabic flagged"),
        ("The Þrymr daemon runs every 15 min", False, "Thorn Þ passes"),
    ]
    print("Language Filter Hook — Self-Test")
    all_ok = True
    for text, expect_violation, desc in tests:
        has_v, names, count = has_blocked_script(text)
        ok = has_v == expect_violation
        all_ok = all_ok and ok
        print(f"  {'OK' if ok else 'FAIL'} | {desc}: {count} violations, expected={expect_violation}")
    print(f"\n{'ALL PASSED' if all_ok else 'SOME FAILED'}")