from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.runtime import get_runtime


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Warm the shared runtime once during startup so the first request
    # does not race on lazy initialization.
    get_runtime()
    yield


app = FastAPI(title="OpenNovel Agent", version="0.1.0", lifespan=lifespan)
app.include_router(router)
