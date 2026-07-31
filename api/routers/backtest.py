from fastapi import APIRouter, Query
from backtest_betting import run_backtest_data

router = APIRouter()

@router.get("/backtest")
async def get_backtest(
    league: str = Query("LPL"),
    model: str = Query("rf"),
    matches: int = Query(50),
    bankroll: float = Query(1000.0),
    fractional: float = Query(0.5),
    margin: float = Query(0.05)
):
    data = run_backtest_data(
        league=league,
        model_type=model,
        initial_bankroll=bankroll,
        fractional=fractional,
        num_matches=matches,
        margin=margin
    )
    return data
