from fastapi import FastAPI
from routes.cleaning import router as cleaning_router
from routes.analytics import router as analytics_router
from routes.ai import router as ai_router

app = FastAPI(title="CleanSight API")

app.include_router(cleaning_router)
app.include_router(analytics_router)
app.include_router(ai_router)

@app.get("/")
def root():
    return {"message": "CleanSight backend is running"} 