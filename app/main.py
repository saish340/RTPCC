"""FastAPI entrypoint for the RTPCC backend."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers.alerts import router as alerts_router
from app.routers.routing import router as routing_router
from app.routers.simulate import router as simulate_router
from app.routers.venue import router as venue_router

app = FastAPI(title="RTPCC API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logger(request: Request, call_next):
    response = await call_next(request)
    print(f"{request.method} {request.url.path} -> {response.status_code}")
    return response


app.include_router(venue_router)
app.include_router(simulate_router)
app.include_router(routing_router)
app.include_router(alerts_router)


@app.get("/")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
