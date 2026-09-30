import logging
import os

from fastapi import FastAPI

from app.api.routes import router

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Data Plumber",
    version="0.1.0",
    description="Adapt arbitrary upstream payloads into the JSON Schema the next workflow step expects.",
)
app.include_router(router)
