from fastapi import FastAPI
from routes.cleaning import router as cleaning_router  # Import the router object
from routes.analytics import router as analytics_router
from routes.ai import router as ai_router

app = FastAPI()

app.include_router(cleaning_router)
app.include_router(analytics_router)
app.include_router(ai_router)

@app.get("/")
def root():
    return {"message": "CleanSight running"}

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# ... your existing code ...

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    with open("frontend/dashboard.html", "r", encoding="utf-8") as f:
        return f.read() 

from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def home():
    with open("frontend/home.html", "r", encoding="utf-8") as f:
        return f.read()