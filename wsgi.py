"""
Credofy Universal Production Entrypoint (WSGI / ASGI)
Compatible with Render, Railway, Heroku, Uvicorn, and Gunicorn
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from backend.server import app

# Standard WSGI / ASGI callable aliases
application = app

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.server:app", host="0.0.0.0", port=port)
