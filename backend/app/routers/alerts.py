from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Alert, Ticker
from app.schemas import AlertOut

router = APIRouter(prefix="/v1")


@router.get("/alerts", response_model=list[AlertOut])
def alerts(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Alert, Ticker.symbol).join(Ticker).order_by(Alert.computed_at.desc(), Alert.id.desc()).limit(limit)
    ).all()
    return [
        AlertOut(
            symbol=symbol, computed_at=a.computed_at, from_band=a.from_band, to_band=a.to_band,
            from_score=a.from_score, to_score=a.to_score,
            direction="up" if a.to_score > a.from_score else "down",
        )
        for a, symbol in rows
    ]
