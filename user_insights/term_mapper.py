"""Term alignment: map variant entity names to canonical forms.

Prevents narrative distortion from counting "VS Code Copilot",
"GitHub Copilot", and "Copilot" as separate entities.
"""

# Canonical entity mapping
ENTITY_ALIASES: dict[str, list[str]] = {
    "GitHub Copilot": [
        "VS Code Copilot", "vscode copilot", "copilot", "github copilot",
        "gh copilot", "ms copilot", "microsoft copilot", "co-pilot",
    ],
    "Cursor": [
        "cursor ai", "cursor ide", "cursor editor",
    ],
    "Claude Code": [
        "claude code", "claude cli", "anthropic claude code", "claude-code",
        "claude agent", "claude-code cli",
    ],
    "Claude": [
        "claude ai", "claude sonnet", "anthropic claude",
    ],
    "OpenAI Codex": [
        "codex", "openai codex", "codex cli", "openai codex cli", "gpt codex",
        "codex agent", "codex sdk",
    ],
    "ChatGPT": [
        "chatgpt", "chat gpt", "openai chatgpt", "gpt-4", "gpt-3.5",
    ],
}

# Normalize to lowercase lookup
CANONICAL_LOOKUP: dict[str, str] = {}
for canonical, aliases in ENTITY_ALIASES.items():
    for alias in aliases:
        CANONICAL_LOOKUP[alias.lower().strip()] = canonical


def map_entity(name: str) -> str:
    """Map a variant entity name to its canonical form.

    Returns the original name if no mapping exists.
    """
    key = name.lower().strip()
    # Direct match
    if key in CANONICAL_LOOKUP:
        return CANONICAL_LOOKUP[key]
    # Partial match: check if any alias is a substring
    for alias, canonical in CANONICAL_LOOKUP.items():
        if alias in key:
            return canonical
    return name


def normalize_features(features: list[str]) -> list[str]:
    """Map a list of feature/entity names to canonical forms, deduplicate."""
    mapped = [map_entity(f) for f in features]
    seen = set()
    result = []
    for m in mapped:
        if m.lower() not in seen:
            seen.add(m.lower())
            result.append(m)
    return result


def normalize_text(text: str) -> str:
    """Replace all known entity aliases in a text with canonical forms."""
    result = text
    # Sort by length descending to match longer phrases first
    sorted_aliases = sorted(CANONICAL_LOOKUP.items(), key=lambda x: -len(x[0]))
    for alias, canonical in sorted_aliases:
        # Case-insensitive replacement
        pattern = alias
        idx = result.lower().find(pattern)
        if idx >= 0:
            # Replace preserving original case context
            result = result[:idx] + canonical + result[idx + len(pattern):]
    return result
