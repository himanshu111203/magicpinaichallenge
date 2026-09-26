"""
Entry point for running the Vera Message Engine bot.

Usage:
    uvicorn bot:app --host 0.0.0.0 --port 8080
"""

from src.engine.composer import compose
from src.main import app

__all__ = ["app", "compose"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=8080, reload=True)

