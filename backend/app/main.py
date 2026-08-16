"""FastAPI application entrypoint.

Phase 0 provides a health probe and serves the static dashboard shell.
Phase A mounts the full API routers (auth, jobs, printers, materials, audit).
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import __version__

app = FastAPI(title="Secure 3D-Printer Fleet API", version=__version__)


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "secure-3dprinter-fleet",
            "version": __version__,
        }
    )


def _mount_static() -> None:
    """Serve the vanilla-JS dashboard from ../frontend if present."""
    frontend = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
    frontend = os.path.abspath(frontend)
    if os.path.isdir(frontend):
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")


_mount_static()
