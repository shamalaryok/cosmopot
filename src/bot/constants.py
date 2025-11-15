"""Shared constants for the Telegram bot module."""

from __future__ import annotations

DEFAULT_CATEGORIES: list[str] = [
    "Portrait",
    "Landscape",
    "Product",
    "Concept Art",
]

PROMPTS_BY_CATEGORY: dict[str, list[str]] = {
    "Portrait": [
        "Cinematic lighting portrait of a character",
        "Hyper-realistic studio headshot with soft light",
        "Painterly renaissance inspired portrait",
    ],
    "Landscape": [
        "Golden hour vista over rolling hills",
        "Futuristic city skyline at dusk",
        "Mystical forest with volumetric light",
    ],
    "Product": [
        "Minimal product shot on marble background",
        "Creative flat lay with complementary props",
        "Dramatic macro shot with rim lighting",
    ],
    "Concept Art": [
        "Hero character concept with dynamic pose",
        "Alien world matte painting with twin suns",
        "Epic battle scene with motion blur",
    ],
}

PARAMETER_PRESETS: dict[str, dict[str, object]] = {
    "fast": {
        "title": "Fast draft",
        "description": "Quick iteration, suitable for previews.",
        "settings": {"quality": "fast", "cfg_scale": 5, "steps": 20},
    },
    "balanced": {
        "title": "Balanced",
        "description": "Good balance between speed and fidelity.",
        "settings": {"quality": "balanced", "cfg_scale": 7, "steps": 30},
    },
    "detailed": {
        "title": "High detail",
        "description": "Maximum detail with longer render time.",
        "settings": {"quality": "detailed", "cfg_scale": 9, "steps": 40},
    },
}

MAX_IMAGE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png"}
ALLOWED_IMAGE_MIME_TYPES: set[str] = {"image/jpeg", "image/png"}
