from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from routers import (
    inserate_ultra as inserate,
    inserat,
    inserate_detailed_ultra as inserate_detailed,
    seller,
)
from utils.browser import OptimizedPlaywrightManager
from utils.asyncio_optimizations import EventLoopOptimizer

# Global browser manager instance for sharing across all endpoints
browser_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown events"""
    global browser_manager

    # Setup uvloop for maximum performance (2-4x improvement)
    uvloop_enabled = EventLoopOptimizer.setup_uvloop()

    # Optimize event loop settings
    EventLoopOptimizer.optimize_event_loop()

    # Startup: Initialize shared browser manager with optimized settings.
    # Chromium is fully restarted every BROWSER_RECYCLE_EVERY scrape ops
    # (default 10_000) to avoid long-lived browser degradation.
    browser_manager = OptimizedPlaywrightManager(max_contexts=20, max_concurrent=3)
    await browser_manager.start()

    # Store browser manager in app state for access by routers
    app.state.browser_manager = browser_manager
    app.state.uvloop_enabled = uvloop_enabled

    yield

    # Shutdown: Clean up browser resources
    if browser_manager:
        await browser_manager.close()


app = FastAPI(version="1.0.0", lifespan=lifespan)


class _RecycleHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        mgr = getattr(request.app.state, "browser_manager", None)
        if mgr is not None:
            metrics = mgr.get_performance_metrics()
            response.headers["X-Recycle-Every"] = str(metrics["recycle_every"])
            response.headers["X-Requests-Since-Recycle"] = str(
                metrics["requests_since_recycle"]
            )
            response.headers["X-Recycle-Count"] = str(metrics["recycle_count"])
        return response


app.add_middleware(_RecycleHeadersMiddleware)


class RecycleEveryBody(BaseModel):
    recycle_every: int = Field(..., ge=1)


@app.post("/browser/recycle-every")
async def set_recycle_every(body: RecycleEveryBody):
    """Set Chromium recycle interval (scrape count). Runtime only; not env."""
    if browser_manager is None:
        raise HTTPException(status_code=503, detail="browser not ready")
    try:
        browser_manager.set_recycle_every(body.recycle_every)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"browser": browser_manager.get_performance_metrics()}


@app.get("/")
async def root():
    metrics = {}
    if browser_manager is not None:
        metrics = browser_manager.get_performance_metrics()
    return {
        "message": "Welcome to the Kleinanzeigen API",
        "endpoints": [
            "/inserate",
            "/inserat/{id}",
            "/inserate-detailed",
            "/seller/{user_id}",
        ],
        "status": "operational",
        "browser": {
            "recycle_every": metrics.get("recycle_every"),
            "total_requests": metrics.get("total_requests"),
            "requests_since_recycle": metrics.get("requests_since_recycle"),
            "browser_generations": metrics.get("browser_generations"),
            "recycle_count": metrics.get("recycle_count"),
        },
    }


app.include_router(inserate.router)
app.include_router(inserat.router)
app.include_router(inserate_detailed.router)
app.include_router(seller.router)
