"""Minimal server for testing the Deezer preview endpoint without DB/Redis."""
from fastapi import FastAPI
from aiblock.api.deezer_preview import router

app = FastAPI(title="AIBlock - Deezer Preview")
app.include_router(router)
