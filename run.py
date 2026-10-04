#!/usr/bin/env python3
"""Development entry point: python run.py (see README for production)."""
import os

from dotenv import load_dotenv

from app import create_app

load_dotenv()
app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    # Debug/dev server only. Serve production behind a real WSGI server
    # (gunicorn/uwsgi) with HTTPS so SESSION_COOKIE_SECURE can be enabled.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=True)
