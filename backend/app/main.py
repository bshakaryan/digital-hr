from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.modules import academy, assistant, audit, auth, calendar, documentolog, employees, knowledge_files, lifecycle, notifications, requests, zup

app = FastAPI(title="JanaМен Digital HR", version="0.3.0", description="Демонстрационный HR-прототип. Кадровые данные и база знаний вымышленные.")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins.split(","), allow_credentials=False, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])
for module in (auth, employees, calendar, requests, lifecycle, academy, notifications, knowledge_files, assistant, audit, zup, documentolog):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health", tags=["health"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
