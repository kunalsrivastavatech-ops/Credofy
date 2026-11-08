"""
Render Default Start Command Fallback Shim
If Render starts with 'gunicorn your_application.wsgi', this exports the ASGI/WSGI app seamlessly.
"""
from wsgi import app, application
wsgi = app
