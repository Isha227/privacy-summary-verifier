from __future__ import annotations

import os

import requests

from .common import ROOT  # noqa: F401 - importing loads the project .env


def main() -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")
    response = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": api_key},
        timeout=60,
    )
    response.raise_for_status()
    for model in response.json().get("models", []):
        if "generateContent" in model.get("supportedGenerationMethods", []):
            print(model["name"].split("/")[-1])


if __name__ == "__main__":
    main()
