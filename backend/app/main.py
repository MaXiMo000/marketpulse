from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import tickers

app = FastAPI(title="MarketPulse")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(tickers.router)


@app.get("/health")
def health():
    return {"status": "ok"}
