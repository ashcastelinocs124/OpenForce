from fastapi import FastAPI

from openforce.api.health import router as health_router

app = FastAPI(title="Openforce", version="0.1.0")
app.include_router(health_router)
