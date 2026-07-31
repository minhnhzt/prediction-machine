from fastapi import APIRouter, Query
from typing import Optional
from schedule_predict import predict_schedule_data
from feature_engineering import DB_PATH

router = APIRouter()

@router.get("/schedule")
async def get_schedule(
    league: str = Query("LPL"),
    model: str = Query("rf"),
    no_cache: bool = Query(False),
    bankroll: float = Query(1000.0)
):
    use_cache = not no_cache
    data = predict_schedule_data(
        league=league,
        model_type=model,
        db_path=DB_PATH,
        use_cache=use_cache,
        bankroll=bankroll
    )
    return data
