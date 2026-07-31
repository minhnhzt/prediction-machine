from fastapi import APIRouter
from pydantic import BaseModel
from kelly_criterion import kelly_criterion

router = APIRouter()

class KellyRequest(BaseModel):
    win_probability: float
    decimal_odds: float
    bankroll: float
    fractional: float = 0.5

@router.post("/kelly/calculate")
async def calculate_kelly(req: KellyRequest):
    kc = kelly_criterion(
        prob_win=req.win_probability,
        odds=req.decimal_odds,
        bankroll=req.bankroll,
        fractional=req.fractional
    )
    return {
        "full_kelly_fraction": kc.full_kelly_fraction,
        "applied_fraction": kc.applied_fraction,
        "wager_pct": kc.wager_pct,
        "wager_amount": kc.wager_amount,
        "edge": kc.edge,
        "expected_value": kc.expected_value,
        "fractional_multiplier": kc.fractional_multiplier,
        "summary": kc.summary()
    }
