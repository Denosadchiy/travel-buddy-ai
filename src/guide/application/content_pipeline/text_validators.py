"""
Text validators for Content Pipeline — post-generation quality checks.

- has_wrong_alphabet: detect mixed-language text
- numbers_to_words: convert digits to spoken form for natural TTS
  (with Russian grammatical case handling for years and centuries)
"""
from __future__ import annotations

import re
from typing import Literal

# Allowed Latin words in Russian text (brands, abbreviations, Roman numerals)
_ALLOWED_LATIN_IN_RU = {
    "GUM", "WiFi", "GPS", "UNESCO", "VIP", "DJ", "PDF", "URL",
    "iPhone", "iPad", "Android", "Google", "Apple", "ElevenLabs",
    "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII", "XIII", "XIV", "XV", "XVI",
    "XVII", "XVIII", "XIX", "XX", "XXI",
}

_ROMAN_MAP = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8,
    "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
    "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20, "XXI": 21,
}


def has_wrong_alphabet(
    text: str, target_language: Literal["en", "ru"]
) -> tuple[bool, list[str]]:
    """
    Check if text contains words in the wrong alphabet.
    Returns (has_issues, list_of_wrong_words).
    """
    if target_language == "ru":
        wrong = re.findall(r"\b[a-zA-Z]{3,}\b", text)
        wrong = [w for w in wrong if w not in _ALLOWED_LATIN_IN_RU]
        return (len(wrong) > 0, wrong)
    elif target_language == "en":
        wrong = re.findall(r"\b[а-яёА-ЯЁ]{3,}\b", text)
        return (len(wrong) > 0, wrong)
    return (False, [])


def _to_prepositional(word: str) -> str:
    """Convert Russian ordinal nominative ('двенадцатый') to prepositional ('двенадцатом')."""
    if word.endswith("ый"):
        return word[:-2] + "ом"
    if word.endswith("ий"):
        return word[:-2] + "ем"
    if word.endswith("ой"):
        return word[:-2] + "ом"
    return word


def _to_genitive(word: str) -> str:
    """Convert Russian ordinal nominative ('двенадцатый') to genitive ('двенадцатого')."""
    if word.endswith("ый"):
        return word[:-2] + "ого"
    if word.endswith("ий"):
        return word[:-2] + "его"
    if word.endswith("ой"):
        return word[:-2] + "ого"
    return word


def numbers_to_words_ru(text: str) -> str:
    """
    Convert digits to words for Russian TTS with grammatical case handling.

    Examples:
      "в 1912 году" → "в тысяча девятьсот двенадцатом году"
      "1866 года" → "тысяча восемьсот шестьдесят шестого года"
      "XVII веке" → "семнадцатом веке"
      "700 000" → "семьсот тысяч"
    """
    try:
        from num2words import num2words as n2w
    except ImportError:
        return text

    # 1. Year with preposition "в/с/до/после/около ... году/года/годов"
    def _replace_year_with_prep(match: re.Match) -> str:
        prep = match.group(1)
        year = int(match.group(2))
        suffix = match.group(3).lower()
        try:
            word = n2w(year, lang="ru", to="ordinal")
            if suffix.startswith("год"):
                if suffix in ("году",):
                    word = _to_prepositional(word)
                elif suffix in ("года", "годов"):
                    word = _to_genitive(word)
            return f"{prep} {word} {match.group(3)}"
        except Exception:
            return match.group(0)

    text = re.sub(
        r"\b(в|с|до|после|около|с)\s+(\d{4})\s+(год[а-яё]*)",
        _replace_year_with_prep,
        text,
        flags=re.IGNORECASE,
    )

    # 2. Year + standalone "году/года/годов" (without preposition)
    def _replace_year_with_suffix(match: re.Match) -> str:
        year = int(match.group(1))
        suffix = match.group(2).lower()
        try:
            word = n2w(year, lang="ru", to="ordinal")
            if suffix == "году":
                word = _to_prepositional(word)
            elif suffix in ("года", "годов"):
                word = _to_genitive(word)
            return f"{word} {match.group(2)}"
        except Exception:
            return match.group(0)

    text = re.sub(
        r"\b(\d{4})\s+(год[а-яё]*)",
        _replace_year_with_suffix,
        text,
    )

    # 3. Standalone years
    def _replace_year(match: re.Match) -> str:
        year = int(match.group(0))
        if 1000 <= year <= 2100:
            try:
                word = n2w(year, lang="ru", to="ordinal")
                return _to_prepositional(word)
            except Exception:
                return match.group(0)
        return match.group(0)

    text = re.sub(r"\b\d{4}\b", _replace_year, text)

    # 4. Roman numerals + век (centuries)
    def _replace_century(match: re.Match) -> str:
        roman = match.group(1)
        suffix = match.group(2)
        num = _ROMAN_MAP.get(roman)
        if num:
            word = n2w(num, lang="ru", to="ordinal")
            if suffix.lower() == "веке":
                word = _to_prepositional(word)
            elif suffix.lower() in ("века", "веков"):
                word = _to_genitive(word)
            return f"{word} {suffix}"
        return match.group(0)

    text = re.sub(
        r"\b(X{0,3}(?:IX|IV|VIII|VII|VI|V|III|II|I))\s+(век[а-яё]*)",
        _replace_century,
        text,
    )

    # 5. Other numbers (1-3 digits, possibly with thousand separator spaces)
    def _replace_number(match: re.Match) -> str:
        num_str = match.group(0).replace(" ", "").replace("\u00a0", "")
        try:
            return n2w(int(num_str), lang="ru")
        except Exception:
            return match.group(0)

    # Numbers with thousand separators: "700 000"
    text = re.sub(r"\b\d{1,3}(?:[\s\u00a0]\d{3})+\b", _replace_number, text)
    # Plain 1-3 digit numbers
    text = re.sub(r"\b\d{1,3}\b", _replace_number, text)

    return text


def numbers_to_words_en(text: str) -> str:
    """Convert digits to words for English TTS."""
    try:
        from num2words import num2words as n2w
    except ImportError:
        return text

    def _replace_year(match: re.Match) -> str:
        year = int(match.group(0))
        if 1000 <= year <= 2100:
            try:
                return n2w(year, lang="en", to="year")
            except Exception:
                return match.group(0)
        return match.group(0)

    def _replace_number(match: re.Match) -> str:
        try:
            return n2w(int(match.group(0)), lang="en")
        except Exception:
            return match.group(0)

    text = re.sub(r"\b\d{4}\b", _replace_year, text)
    text = re.sub(r"\b\d{1,3}\b", _replace_number, text)
    return text


def numbers_to_words(text: str, language: Literal["en", "ru"]) -> str:
    """Dispatch to language-specific number conversion."""
    if language == "ru":
        return numbers_to_words_ru(text)
    return numbers_to_words_en(text)


def count_number_replacements(text: str, language: Literal["en", "ru"]) -> int:
    """Count how many numbers would be replaced."""
    return len(re.findall(r"\b\d+\b", text))


# =========================================================================
# Comprehensive text quality validation (Step 12.9)
# =========================================================================

_ALLOWED_CHARS_RU = set(
    " \n\t\r"
    "0123456789"
    ".,;:!?-—–()«»\"\"''…\""
    "%№°²³"
)
_ALLOWED_LATIN_WORDS_UPPER = {
    "GUM", "WIFI", "GPS", "USB", "DJ", "VIP", "PR", "IT", "MP3",
    "URL", "API", "SMS", "TV", "FM", "AM", "CD", "DVD", "PC", "OK",
    "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII", "XIII", "XIV", "XV",
    "XVI", "XVII", "XVIII", "XIX", "XX", "XXI",
}


def validate_text_quality_ru(text: str) -> tuple[bool, list[str]]:
    """
    Comprehensive Russian text quality check.
    Returns (is_clean, list_of_issues).
    """
    issues: list[str] = []

    # 1. Foreign-alphabet characters (not Cyrillic, not digits, not punctuation)
    foreign_chars = []
    for i, ch in enumerate(text):
        if ch in _ALLOWED_CHARS_RU:
            continue
        if "\u0400" <= ch <= "\u04FF" or "\u0500" <= ch <= "\u052F":
            continue  # Cyrillic
        if "a" <= ch.lower() <= "z":
            continue  # Latin handled below
        # Anything else is suspicious
        foreign_chars.append((i, ch, ord(ch)))
    if foreign_chars:
        sample = ", ".join(f"'{c[1]}' (U+{c[2]:04X})" for c in foreign_chars[:5])
        issues.append(f"Non-Cyrillic chars: {sample}")

    # 2. Latin chars mixed inside Cyrillic words
    mixed_words = re.findall(r"\b\S*[a-zA-Z]+\S*\b", text)
    cyrillic_mixed = [w for w in mixed_words if re.search(r"[а-яёА-ЯЁ]", w)]
    if cyrillic_mixed:
        issues.append(f"Mixed-alphabet words: {cyrillic_mixed[:5]}")

    # 3. Any Latin letters (1+) not in allow-list
    latin_words = re.findall(r"\b[a-zA-Z]+\b", text)
    wrong_latin = [w for w in latin_words if w.upper() not in _ALLOWED_LATIN_WORDS_UPPER]
    if wrong_latin:
        issues.append(f"Latin words: {wrong_latin[:5]}")

    # 4. Repeated words (LLM stutter)
    repeated = re.findall(r"\b(\w{3,})\s+\1\b", text, re.IGNORECASE)
    if repeated:
        issues.append(f"Repeated words: {repeated[:3]}")

    return (len(issues) == 0, issues)


def validate_text_quality_en(text: str) -> tuple[bool, list[str]]:
    """Comprehensive English text quality check."""
    issues: list[str] = []
    cyrillic = re.findall(r"[а-яёА-ЯЁ]+", text)
    if cyrillic:
        issues.append(f"Cyrillic in English: {cyrillic[:5]}")
    repeated = re.findall(r"\b(\w{3,})\s+\1\b", text, re.IGNORECASE)
    if repeated:
        issues.append(f"Repeated words: {repeated[:3]}")
    return (len(issues) == 0, issues)


def auto_fix_text_ru(text: str) -> str:
    """
    Auto-fix common Russian text artifacts.
    - Strip non-Cyrillic chars (keeps digits, basic punctuation)
    - Strip Latin letters mixed inside Cyrillic words
    - Collapse double spaces
    """
    # Allow: Cyrillic block, Cyrillic supplement, digits, basic punct, spaces
    allowed_pattern = r"[^\u0400-\u04FF\u0500-\u052F0-9\s.,;:!?—–\-()«»\"\"''…\"%№°²³a-zA-Z]"
    cleaned = re.sub(allowed_pattern, "", text)

    # Remove Latin letters that are inside Cyrillic words (mixed-alphabet artifact)
    def _strip_latin_in_mixed(match: re.Match) -> str:
        word = match.group(0)
        if re.search(r"[а-яёА-ЯЁ]", word):
            return re.sub(r"[a-zA-Z]+", "", word)
        return word

    cleaned = re.sub(r"\S+", _strip_latin_in_mixed, cleaned)

    # Collapse multiple spaces
    cleaned = re.sub(r" {2,}", " ", cleaned)
    # Fix space-before-punct artifacts
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    return cleaned.strip()


def auto_fix_text_en(text: str) -> str:
    """Auto-fix English text — strip Cyrillic chars, normalize spaces."""
    cleaned = re.sub(r"[\u0400-\u04FF\u0500-\u052F]+", "", text)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    return cleaned.strip()


def auto_fix(text: str, language: Literal["en", "ru"]) -> str:
    """Dispatch to language-specific auto-fix."""
    return auto_fix_text_ru(text) if language == "ru" else auto_fix_text_en(text)


def validate_text_quality(text: str, language: Literal["en", "ru"]) -> tuple[bool, list[str]]:
    """Dispatch to language-specific validator."""
    return validate_text_quality_ru(text) if language == "ru" else validate_text_quality_en(text)


def has_vague_person_references(text: str, language: str = "ru") -> tuple[bool, list[str]]:
    """Check for unnamed 'famous' people (vague references without full names)."""
    if language != "ru":
        return (False, [])
    patterns = [
        r"(?:известн|знаменит|выдающ)[а-яё]+\s+(?:художник|архитектор|писател|музыкант|поэт|деятел|москвич|артист|композитор|скульптор)",
        r"(?:многие|несколько|ряд)\s+(?:известн|знаменит|выдающ)[а-яё]+",
        r"(?:творческ|культурн)[а-яё]+\s+(?:люд[а-яё]+|личност[а-яё]+|деятел[а-яё]+)",
    ]
    issues: list[str] = []
    for p in patterns:
        matches = re.findall(p, text, re.IGNORECASE)
        issues.extend(matches)
    return (len(issues) > 0, issues)


def has_broken_russian(text: str) -> tuple[bool, list[str]]:
    """Detect obviously broken Russian text (merged words, truncated names)."""
    issues: list[str] = []
    # Very long words = probably merged
    long = re.findall(r"\b[а-яё]{15,}\b", text)
    if long:
        issues.append(f"Merged words: {long[:3]}")
    # Orphan word endings (truncated names like "овском переулке")
    orphans = re.findall(r"\b[а-яё]{1,3}(?:ском|ской|овском|евском)\s+переулк", text, re.IGNORECASE)
    if orphans:
        issues.append(f"Truncated names: {orphans[:3]}")
    return (len(issues) > 0, issues)


def has_arabic_or_roman_numerals(text: str) -> tuple[bool, list[str]]:
    """
    Check that text contains no Arabic digits or Roman numerals.
    For TTS, numbers must be written as words.
    Returns (has_issues, list_of_issues).
    """
    issues: list[str] = []
    arabic = re.findall(r"\b\d+\b", text)
    if arabic:
        issues.append(f"Arabic numerals: {arabic[:5]}")
    # Roman numerals as standalone tokens (not inside words)
    roman = re.findall(r"\b(?:X{1,3}(?:IX|IV|V?I{0,3})|IX|IV|V?I{2,3}|II)\b", text)
    if roman:
        issues.append(f"Roman numerals: {roman[:5]}")
    return (len(issues) > 0, issues)
