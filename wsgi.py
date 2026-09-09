"""Gunicorn entrypoint; importing this module never opens a listening socket."""
from app import create_app

app = create_app()
