"""FastAPI application entrypoint for the ui-dashboard backend."""
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .db import DatabaseError

app = FastAPI(title="ui-dashboard API", version="0.1.0")

_allowed = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DatabaseError)
async def _db_error_handler(request: Request, exc: DatabaseError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": f"Database error: {exc}"})


@app.exception_handler(ValueError)
async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"service": "ui-dashboard", "docs": "/docs", "api": "/api"}
