# string_utils.py
"""
Utility functions for transforming strings into different naming conventions.
Useful for AWS CDK naming (PascalCase, camelCase, kebab-case, etc.).
"""

import re


def kebab_to_pascal(s: str) -> str:
    """Convert kebab-case to PascalCase.
    Example: "eu-west-1a" -> "EuWest1a"
    """
    return "".join(part.capitalize() for part in s.split("-") if part)


def kebab_to_camel(s: str) -> str:
    """Convert kebab-case to camelCase.
    Example: "eu-west-1a" -> "euWest1a"
    """
    pascal = kebab_to_pascal(s)
    return pascal[0].lower() + pascal[1:] if pascal else pascal


def to_kebab(s: str) -> str:
    """Convert PascalCase or camelCase to kebab-case.
    Example: "EuWest1a" -> "eu-west-1a"
    """
    s = re.sub("([a-z0-9])([A-Z])", r"\1-\2", s)
    return s.replace("_", "-").lower()


def sanitize_for_cfn(s: str) -> str:
    """Ensure string is CloudFormation-safe (letters & numbers only).
    Removes invalid characters.
    """
    return re.sub(r"[^A-Za-z0-9]", "", s)


def to_pascal(s: str) -> str:
    """
    Convert any naming convention to PascalCase.

    Handles:
    - kebab-case: "fr-dev" -> "FrDev"
    - snake_case: "fr_dev" -> "FrDev"
    - camelCase: "frDev" -> "FrDev"
    - Mixed: "fr-dev_stage" -> "FrDevStage"
    - Spaces: "fr dev" -> "FrDev"
    - Already PascalCase: "FrDev" -> "FrDev"

    Args:
        s: String in any common naming convention

    Returns:
        String in PascalCase

    Examples:
        >>> to_pascal("fr-dev")
        'FrDev'
        >>> to_pascal("fr_dev")
        'FrDev'
        >>> to_pascal("fr-dev_stage")
        'FrDevStage'
        >>> to_pascal("FrDev")
        'FrDev'
        >>> to_pascal("frDev")
        'FrDev'
    """
    if not s:
        return s

    # Step 1: Replace all separators (-, _, space) with a common delimiter
    normalized = s.replace("_", "-").replace(" ", "-")

    # Step 2: Insert hyphens before uppercase letters for camelCase/PascalCase
    # "FrDev" -> "Fr-Dev", "frDev" -> "fr-Dev"
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", normalized)

    # Step 3: Split on hyphens and capitalize each part
    parts = [part.capitalize() for part in normalized.split("-") if part]

    # Step 4: Join all parts
    return "".join(parts)
