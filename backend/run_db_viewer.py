"""
Standalone Database Viewer Runner for AIDincharya
Runs an isolated Database Viewer server on http://localhost:8005 without connecting to the main application frontend or main nav bar.
"""

import sys
import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Add parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database import db

app = FastAPI(title="AIDincharya Database Inspector - Standalone")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "static")

@app.get("/", response_class=HTMLResponse)
@app.get("/db-viewer", response_class=HTMLResponse)
def serve_db_viewer():
    filepath = os.path.join(STATIC_DIR, "db_viewer.html")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="db_viewer.html not found")
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/admin/db/tables")
def get_tables():
    return {"tables": db.get_tables()}

@app.get("/api/admin/db/table/{table_name}")
def get_table_data(table_name: str, limit: int = 100, offset: int = 0, search: str = None):
    result = db.get_table_data(table_name, limit=limit, offset=offset, search=search)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

if __name__ == "__main__":
    print("=" * 60)
    print("⚡ Starting AIDincharya Standalone Database Inspector Website...")
    print("📍 URL: http://localhost:8005")
    print("=" * 60)
    uvicorn.run("run_db_viewer:app", host="0.0.0.0", port=8005, reload=True)
