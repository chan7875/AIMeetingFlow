import os
import sys
from contextlib import asynccontextmanager

# Allow importing from project root
sys.path.insert(0, str(__file__).rsplit("/web/", 1)[0])

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from web.routers import files as files_router
from web.routers import ai as ai_router
from web.routers import git as git_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ai_router.start_auto_watch()
    try:
        yield
    finally:
        await ai_router.stop_auto_watch()


app = FastAPI(title="Obsidian Vault Viewer", version="1.0.0", lifespan=lifespan)

# API routers
app.include_router(files_router.router)
app.include_router(ai_router.router)
app.include_router(git_router.router)

# Static files
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8101))
    uvicorn.run("web.main:app", host="0.0.0.0", port=port, reload=True)
