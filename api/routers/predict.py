from fastapi import APIRouter
from pydantic import BaseModel
import numpy as np
from feature_engineering import get_latest_team_stats, DB_PATH
from schedule_predict import train_model_for_league, get_team_features, normalize_name

router = APIRouter()

class PredictRequest(BaseModel):
    blue_team: str
    red_team: str
    league: str = "LPL"
    model: str = "lr"

@router.post("/predict/hypothetical")
async def predict_hypothetical(req: PredictRequest):
    # 1. Get stats
    latest_stats, name_to_id = get_latest_team_stats(DB_PATH, league_filter=req.league)
    
    # 2. Get team features
    blue_db_name = normalize_name(req.blue_team)
    red_db_name = normalize_name(req.red_team)
    
    blue_feats, blue_fallback = get_team_features(blue_db_name, latest_stats, name_to_id)
    red_feats, red_fallback = get_team_features(red_db_name, latest_stats, name_to_id)
    
    # 3. Train model
    try:
        model, scaler = train_model_for_league(req.league, model_type=req.model, db_path=DB_PATH)
    except Exception as e:
        return {"error": f"Failed to train model for {req.league}: {str(e)}"}
        
    # 4. Predict
    input_vector = np.array([[
        blue_feats["Elo"], red_feats["Elo"],
        blue_feats["ObjCtrl"], red_feats["ObjCtrl"],
        blue_feats["AvgKills"], red_feats["AvgKills"],
        blue_feats["AvgDuration"], red_feats["AvgDuration"],
        blue_feats["AvgDragons"], red_feats["AvgDragons"],
        blue_feats["AvgTowers"], red_feats["AvgTowers"],
        blue_feats["AvgGold"], red_feats["AvgGold"],
        0.50, 0.50
    ]])
    input_scaled = scaler.transform(input_vector)
    proba = model.predict_proba(input_scaled)[0]
    pred_class = model.predict(input_scaled)[0]
    
    pred_winner = req.blue_team if pred_class == 1 else req.red_team
    winner_prob = proba[1] if pred_class == 1 else proba[0]
    
    return {
        "blue_team": req.blue_team,
        "red_team": req.red_team,
        "blue_fallback_used": blue_fallback,
        "red_fallback_used": red_fallback,
        "predicted_winner": pred_winner,
        "winner_prob": float(winner_prob),
        "blue_prob": float(proba[1]),
        "red_prob": float(proba[0])
    }
