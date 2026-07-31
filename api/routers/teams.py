from fastapi import APIRouter, Query
from feature_engineering import get_latest_team_stats, DB_PATH

router = APIRouter()

@router.get("/teams/stats")
async def get_team_stats(league: str = Query("LPL")):
    latest_stats, name_to_id = get_latest_team_stats(DB_PATH, league_filter=league)
    
    id_to_name = {v: k for k, v in name_to_id.items()}
    
    result = []
    for team_id, stats in latest_stats.items():
        team_name = id_to_name.get(team_id, f"Team {team_id}")
        team_data = {"id": team_id, "name": team_name}
        team_data.update(stats)
        result.append(team_data)
        
    return {"teams": result}
