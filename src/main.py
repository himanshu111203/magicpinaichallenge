from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from src.api.routes import router

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Vera Message Engine",
    description="High-compulsion merchant and customer messaging engine for magicpin AI Challenge",
    version="1.0.0",
)

# Include v1 router
app.include_router(router)

# Mount static files directory
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Ensure malformed incoming JSON gets a clean 400 response matching challenge spec."""
    return JSONResponse(
        status_code=400,
        content={
            "accepted": False,
            "reason": "malformed_request",
            "details": exc.errors(),
        },
    )


@app.get("/")
async def root(request: Request):
    """Serve interactive web dashboard or JSON metadata if requested."""
    index_file = STATIC_DIR / "index.html"
    accept = request.headers.get("accept", "")
    if ("application/json" in accept and "text/html" not in accept) or not index_file.exists():
        return {
            "engine": "Vera Message Engine",
            "status": "online",
            "endpoints": ["/v1/healthz", "/v1/metadata", "/v1/context", "/v1/tick", "/v1/reply"],
            "dashboard": "/dashboard",
        }
    return FileResponse(index_file)


@app.get("/dashboard")
async def dashboard():
    """Direct route for web dashboard."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"status": "dashboard not found"}
