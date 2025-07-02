# ai_route_planner/core/errors.py
from typing import Any, Dict, Optional

class APIError(Exception):
    """Base exception for API-related errors."""
    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}

class DifyError(APIError):
    """Exception for errors specifically from the Dify.ai API."""
    pass

class GeoapifyError(APIError):
    """Exception for errors specifically from the Geoapify API."""
    pass

class GeocodingError(GeoapifyError):
    """Exception for errors during geocoding."""
    pass

class RoutePlanningError(GeoapifyError):
    """Exception for errors during route planning."""
    pass

class InputValidationError(APIError):
    """Exception for validation errors in input data."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, details=details)

class DataProcessingError(APIError):
    """Exception for errors during internal data processing/transformation."""
    pass