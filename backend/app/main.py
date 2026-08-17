"""FastAPI application entrypoint.

Serves the API under /api and the vanilla-JS dashboard at the root path.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .api import router as api_router
from .auth import AccessDenied
from .db import init_db, session_scope
from .jobs import JobError
from .ledger import get_ledger
from .storage import StorageError
from .users import bootstrap_admin


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with session_scope() as s:
        bootstrap_admin(s)
        s.commit()
    yield


app = FastAPI(title="Secure 3D-Printer Fleet API", version=__version__, lifespan=lifespan)


@app.exception_handler(AccessDenied)
def _access_denied(_: Request, exc: AccessDenied):
    # Record the denied attempt in the audit stream (a reverted on-chain call
    # cannot persist a log, so the backend captures it at tier A0).
    try:
        with session_scope() as s:
            get_ledger().append(s, exc.actor, "AccessDenied", exc.action,
                                {"actor": exc.actor, "action": exc.action})
            s.commit()
    except Exception:
        pass
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(JobError)
def _job_error(_: Request, exc: JobError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(StorageError)
def _storage_error(_: Request, exc: StorageError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ValueError)
def _value_error(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "secure-3dprinter-fleet", "version": __version__})


app.include_router(api_router)


def _mount_static() -> None:
    frontend = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
    if os.path.isdir(frontend):
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")


_mount_static()
