# ai_route_planner/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
import logging

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables or .env file.
    """
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    GEOAPIFY_API_KEY: str = ""
    DIFY_API_KEY: str = ""
    DIFY_API_BASE_URL: str = "https://api.dify.ai/v1"
    DIFY_APP_CONVERSATION_ID: str = "" 
    APP_ID: str  = ""

    LOG_LEVEL: str = "INFO"

    @property
    def geoapify_geocoding_url(self) -> str:
        return "https://api.geoapify.com/v1/geocode"

    @property
    def geoapify_route_planner_url(self) -> str:
        return "https://api.geoapify.com/v1/routeplanner"
    
    @property 
    def geoapify_routing_url(self) -> str:
        return "https://api.geoapify.com/v1/routing"

settings = Settings()

# Configure logging
logging.basicConfig(level=settings.LOG_LEVEL,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


if __name__=="__main__":
    print(settings.DIFY_API_KEY)
    print(settings.DIFY_API_BASE_URL)
    print(settings.geoapify_geocoding_url)
    print(settings.geoapify_route_planner_url)
    print(settings.GEOAPIFY_API_KEY)