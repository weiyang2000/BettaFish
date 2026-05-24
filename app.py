"""Compatibility launcher for the BettaFish FastAPI service."""

from __future__ import annotations

import os

import uvicorn

from apps.api.main import app


def main() -> None:
    """Run the versioned SaaS API when users start the project with python app.py."""
    host = os.getenv("BETTAFISH_API_HOST", "0.0.0.0")
    port = int(os.getenv("BETTAFISH_API_PORT", "8000"))
    uvicorn.run("apps.api.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
