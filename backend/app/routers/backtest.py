import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import BacktestRun
from app.schemas import BacktestOut
from app.security import PROTECTED

router = APIRouter(prefix="/v1", dependencies=PROTECTED)


@router.get("/backtest", response_model=BacktestOut)
def latest_backtest(db: Session = Depends(get_db)):
    run = db.scalar(select(BacktestRun).order_by(BacktestRun.id.desc()))
    if run is None:
        raise HTTPException(404, "No backtest has been run yet. Run: python -m app.backtest NVDA AAPL MSFT")
    return BacktestOut(created_at=run.created_at, result=json.loads(run.result))
