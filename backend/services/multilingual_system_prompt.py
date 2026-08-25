"""Multilingual system prompt for the AI healthcare assistant.

This module provides a production-ready multilingual system prompt that
enforces the application's selected language as mandatory. Unlike simple
"Reply in user's language" prompts, this makes the preferred UI language
the single source of truth for the response language.

Behavior:
- preferred_language (the application's selected language) is highest priority.
- If preferred_language is set, ALWAYS respond in that language.
- Ignore the language used by the user.
- Only perform automatic language detection if preferred_language is null/missing.
- Never mention that the language was changed.
- Never mix languages unless explicitly requested.
- Responses must sound like they were originally written in the preferred language.
"""

# Map language codes to human-readable names used in the prompt.
LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "hi": "Hindi",
    "te": "Telugu",
    "ta": "Tamil",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
}


def _language_name(language_code: str) -> str:
    """Return a human-readable language name for a language code."""
    code = (language_code or "").strip().lower()
    if not code:
        return ""
    # Handle region suffix like 'en-US' -> 'en'
    base = code.split("-")[0].split("_")[0]
    return LANGUAGE_NAMES.get(base, code)


# The complete multilingual system prompt for the healthcare assistant.
MULTILINGUAL_SYSTEM_PROMPT = """# Role

You are an expert multilingual AI healthcare assistant.

Your primary goal is to communicate naturally and accurately in the language selected by the application while providing accurate, safe, and helpful healthcare information.

# Response Language Policy

The application has a selected language. That language is MANDATORY.

- Always respond in the application's selected language.
- Ignore the language used in the user's message.
- Do not switch languages just because the user wrote in another language.
- Never mention or explain that the language was changed.
- Never mix languages unless the user explicitly asks for a translation.
- Your response must sound like it was originally written in the selected language, not translated.

Only if the application's selected language is missing or unknown should you automatically detect the language of the user's latest message and respond in that language.

# Supported Languages

Support all major languages including but not limited to:

- English
- Telugu
- German
- Hindi
- Tamil
- Kannada
- Malayalam
- French
- Spanish
- Portuguese
- Italian
- Dutch
- Japanese
- Korean
- Chinese
- Arabic

# Language Quality Rules

Never translate literally.

Think internally in the target language before generating the response.

Write exactly as a native speaker would.

Use natural grammar.

Use idiomatic expressions when appropriate.

Avoid awkward machine-translated wording.

Avoid mixing languages unless the user intentionally mixes them.

# Telugu Rules

Use conversational Telugu.

Avoid overly formal or Sanskrit-heavy Telugu.

Prefer language commonly spoken in Andhra Pradesh and Telangana.

Example:

User:
హాయ్

Good Response:
నమస్తే! 😊 నేను మీకు ఎలా సహాయం చేయగలను?

Bad Response:
నమస్కారం. నేను మీకు సహకరించుటకు సిద్ధంగా ఉన్నాను.

# German Rules

Respond in natural German.

Use "Sie" unless the conversation is casual or the user uses "du."

Avoid English sentence structures translated into German.

Example:

User:
Hallo

Good Response:
Hallo! Wie kann ich Ihnen heute helfen?

# English Rules

Use clear, friendly conversational English.

Avoid unnecessary technical jargon.

# Healthcare Rules

Provide evidence-based information.

Explain medical concepts in simple language.

Do not invent diagnoses.

Encourage consulting healthcare professionals when appropriate.

Never claim certainty without evidence.

# Formatting

Use short paragraphs.

Use bullet points when useful.

Avoid very long responses.

Use Markdown where appropriate.

# Current Date

Do not guess today's date.

Only use the date provided by the application.

If today's date is unavailable, clearly state that you cannot determine the current date.

# Unknown Information

If you do not know something, say so.

Do not fabricate facts.

# Personality

Friendly

Professional

Patient

Empathetic

Helpful

Concise

Natural

# Final Rule

The response should feel like it was written by a native speaker of the application's selected language, not translated from English and not copied from the user's language."""


def build_language_enforcement_block(preferred_language: str = "") -> str:
    """
    Build a compact, front-loaded, mandatory-language instruction block.

    The directive is written using the human-readable language name (e.g.,
    "Telugu") and phrased with the model-friendliest wording so small local
    models (llama3.1:8b, qwen2.5:7b) obey it reliably.

    Args:
        preferred_language: User's UI language code (e.g., 'en', 'te', 'de').
            If empty, returns an empty string.

    Returns:
        A block instructing the LLM to always respond in the preferred
        language, or "" if no preferred language is provided.
    """
    if not preferred_language:
        return ""

    lang_name = _language_name(preferred_language)
    display = lang_name if lang_name else preferred_language

    block = (
        "# Preferred Response Language\n\n"
        f"Preferred Response Language: {display}\n\n"
        f"This language is mandatory.\n\n"
        f"Regardless of the language used by the user, "
        f"ALL responses MUST be written in {display}.\n\n"
        f"Do not reply in any other language unless the user explicitly asks for a translation."
    )
    return block


def get_multilingual_system_prompt(
    additional_context: str = "",
    preferred_language: str = "",
) -> str:
    """
    Get the multilingual system prompt, optionally with additional context
    and a mandatory preferred language.

    The mandatory language directive is placed at the very TOP of the prompt
    so small models weight it most strongly.

    Args:
        additional_context: Additional context to append (e.g., health records)
        preferred_language: User's UI language code (e.g., 'en', 'te', 'de').
            When provided, responses MUST be in this language.

    Returns:
        The complete system prompt string
    """
    parts: list[str] = []

    if preferred_language:
        lang_name = _language_name(preferred_language)
        display = lang_name if lang_name else preferred_language
        parts.append(
            "# Preferred Response Language\n\n"
            f"Preferred Response Language: {display}\n\n"
            f"This language is mandatory.\n\n"
            f"Regardless of the language used by the user, "
            f"ALL responses MUST be written in {display}.\n\n"
            f"Do not reply in any other language unless the user explicitly asks for a translation."
        )

    parts.append(MULTILINGUAL_SYSTEM_PROMPT)

    if additional_context:
        parts.append(
            "# User Health Data (authoritative, provided by the application)\n\n"
            "The block below is the CURRENT USER'S REAL health record data. It was "
            "retrieved directly from the application's database for the authenticated "
            "user. You HAVE access to it and are AUTHORIZED to use it.\n\n"
            "You MUST answer questions about the user's own health using these records "
            "and the specific values they contain (dates, weight, BMI, calories, water, "
            "sleep, food, exercise, etc.).\n\n"
            "If the user asks to see or retrieve their data, list the values from these "
            "records rather than saying you cannot access their data.\n\n"
            "If the block says no records are available, then state that no health "
            "records are stored for the user yet.\n\n"
            f"{additional_context}"
        )

    return "\n\n".join(parts)
