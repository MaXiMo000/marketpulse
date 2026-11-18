from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.routers import alerts, backtest, portfolios, tickers
from app.security import validate_settings

MAX_BODY_BYTES = 16_384


def create_app() -> FastAPI:
    validate_settings(settings)
    dev = settings.app_env == "development"
    app = FastAPI(
        title="MarketPulse",
        docs_url="/docs" if dev else None,
        redoc_url="/redoc" if dev else None,
        openapi_url="/openapi.json" if dev else None,
    )

    def secure(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if not dev:
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    @app.middleware("http")
    async def harden(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            length = request.headers.get("content-length")
            if length is None and "chunked" in request.headers.get("transfer-encoding", "").lower():
                return secure(JSONResponse({"detail": "Content-Length required"}, status_code=411))
            if length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
                return secure(JSONResponse({"detail": "request body too large"}, status_code=413))
        return secure(await call_next(request))

    # added after `harden`, so CORS wraps it and error responses still carry CORS headers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(tickers.router)
    app.include_router(portfolios.router)
    app.include_router(alerts.router)
    app.include_router(backtest.router)

    @app.get("/health")
    def health(db: Session = Depends(get_db)):
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            raise HTTPException(503, "database unavailable")  # no internal detail for an unauthenticated caller
        return {"status": "ok"}

    return app


app = create_app()
