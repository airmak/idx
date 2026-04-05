"""
Production entry point for IDx.
Used by gunicorn / any WSGI server.
"""

from app import app

if __name__ == "__main__":
    app.run()
