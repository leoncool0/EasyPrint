"""
EasyPrint Server - Main Entry Point
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.config import settings
from app.api import router
from app.tcp.gateway import TCPGateway
from app.models.database import init_db

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# TCP Gateway instance
tcp_gateway: TCPGateway = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    global tcp_gateway

    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Start TCP Gateway
    tcp_gateway = TCPGateway()
    tcp_task = asyncio.create_task(
        tcp_gateway.start(settings.TCP_HOST, settings.TCP_PORT)
    )
    logger.info(f"TCP Gateway started on {settings.TCP_HOST}:{settings.TCP_PORT}")

    yield

    # Shutdown
    logger.info("Shutting down...")
    if tcp_gateway:
        await tcp_gateway.stop()
    tcp_task.cancel()
    logger.info("TCP Gateway stopped")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(router, prefix="/api")

# Static files for Web UI
static_dir = os.path.join(os.path.dirname(__file__), "web", "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    """Root endpoint - serve Web UI if available"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HTTP_HOST,
        port=settings.HTTP_PORT,
        reload=settings.DEBUG,
    )