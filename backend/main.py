import os
import uvicorn
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Custom imports
from logger import configure_logging
from routes import all_routers
from utils.middleware import AuthMiddleware
from __init__ import __version__

load_dotenv()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="AssistCX API",
        description="API and routes available in AssistCX backend",
        version=__version__,
    )

    # Add Auth middleware (class-based)
    app.add_middleware(AuthMiddleware)

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include all routes
    all_routers(app)  # or include_routes(app)

    # Startup event
    @app.on_event("startup")
    def startup_event():
        logger = configure_logging(__name__)
        logger.info("Logger is configured.")

        # Create data directory for attachment-worker service
        if os.getenv("SERVICE_TYPE") == "attachment-worker":
            os.makedirs("data", exist_ok=True)

    # Shutdown event
    @app.on_event("shutdown")
    def shutdown_event():
        logger = configure_logging(__name__)
        logger.info("Server is shutting down.")

    # Root endpoint
    @app.get("/")
    async def root():
        return {"message": "AssistCX API is running"}

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    # Favicon endpoint
    @app.get("/favicon.ico")
    async def favicon():
        pass

    return app


# Create FastAPI app
app = create_app()


def start_server(host: Optional[str] = None, port: Optional[int] = None):
    """Start the server.

    Args:
        host: Optional host override
        port: Optional port override
    """
    uvicorn.run(
        "main:app",
        host=host or "0.0.0.0",
        port=port or 8000,
        reload=True,
        timeout_keep_alive=120,
        limit_concurrency=1000,
        limit_max_requests=10000,
        h11_max_incomplete_event_size=4194304,  # 4MB buffer
    )


if __name__ == "__main__":
    start_server()
