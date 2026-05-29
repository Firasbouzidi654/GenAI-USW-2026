from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import prompt, upload

app = FastAPI(title="KI-Lern- & Jobagent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(prompt.router, prefix="/api")
app.include_router(upload.router, prefix="/api")

@app.get("/health")
async def health():
    return {"status": "ok"}