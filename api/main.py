import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import schedule, backtest, teams, kelly, predict

app = FastAPI(title="Prediction Model API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schedule.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(teams.router, prefix="/api")
app.include_router(kelly.router, prefix="/api")
app.include_router(predict.router, prefix="/api")

@app.get("/api/health")
async def health():
    return {"status": "ok"}
