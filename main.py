from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.endpoints import router as api_router
from config import settings, logger


def create_app() -> FastAPI:
    """
    Creates and configures the FastAPI application.
    """
    app = FastAPI(
        title="AI-Powered Backed Route Planner API",
        description="An Intelligent backend API for optimizing delivery and pickup routes using natural language  commands, integrating Dify.ai and Geoapify.",
        version="1.0.0", 
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # Confiure CORS (Cross-Origin Resource Sharing)
    # Allows only trusted domains
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # Allows al origins
        allow_credentials=True,
        allow_methods=["*"], # Allows all methods (GET, POST, etc.)
        allow_headers=["*"], # Allows all headers
    )
    
    # Include the API router
    app.include_router(api_router, prefix="/api/v1")
    
    @app.get("/")
    async def root():
        """
        Root endpoint for the API
        """
        return {"message": "Welcome to the AI-Powered Backend Route Planner API! Access docs at /docs"}
    
    logger.info("FastaPI application initialized")
    return app

app = create_app()
