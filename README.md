## CleanSight

**Real-time hospital hygiene compliance tracking & AI-powered insights**

CleanSight is a web-based system that helps hospitals reduce hospital-acquired infections (HAIs) by providing real-time surface coverage tracking, behavioral analytics, and AI-generated recommendations for cleaning staff.

Built for Hacklytics 2026.

## Features

- **Live Surface Monitoring** (CleanSight tab): Real-time camera feed with overlay grid showing cleaned vs. missed areas
- **Data & Analytics**: Aggregated heat maps of frequently missed zones, average coverage %, total sessions, high-stress session counts
- **AI Insights**: Gemini-powered summaries and recommendations for improving hygiene compliance
- **Backend**: FastAPI + SQLAlchemy + SQLite (local dev) with endpoints for session logging and analytics
- **Frontend**: Modern, responsive single-page dashboard with tab navigation (Home, CleanSight, Data & Analytics)

## Tech Stack

**Backend**
- FastAPI (API framework)
- Uvicorn (ASGI server)
- SQLAlchemy (ORM)
- SQLite (local database: `cleansight.db`)
- Pydantic (data validation)
- python-dotenv (environment variables)
- requests (external API calls, e.g., Gemini)

**Frontend**
- HTML5 + CSS3 (vanilla, no frameworks)
- Vanilla JavaScript (tab switching, data fetching)
- Google Fonts (Inter)
- Responsive grid/flex layout

## Project Structure

cleansight/
├── frontend/
│   ├── dashboard.html        ← main dashboard (Home + tabs)
│   └── images/               ← optional local images
├── routes/
│   ├── init.py
│   ├── cleaning.py
│   ├── analytics.py
│   └── ai.py
├── main.py                   ← FastAPI app entry point
├── database.py               ← engine, session, Base
├── models.py                 ← CleaningSession model
├── init_db.py                ← creates tables
├── .env                      ← GEMINI_API_KEY=your-key
└── README.md


## Setup & Run

1. **Clone the repo**
   ```bash
   git clone <your-repo-url>
   cd cleansight

2. Create virtual environment & install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate   # Linux/Mac
   venv\Scripts\activate      # Windows
   pip install -r requirements.txt

4. Set up environment variables. Create .env in root:
   GEMINI_API_KEY=your-google-gemini-api-key-here

6. Initialize database:
   ```bash
   python init_db.py

7. Run the server:
  uvicorn main:app --reload

8. Open in browser:
http://127.0.0.1:8000/dashboard

Team
Built by CleanSight for Hacklytics 2026.

  

