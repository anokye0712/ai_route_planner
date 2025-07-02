from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Dict, Any

from api.models import RouteRequest, GeoapifyRoutePlannerResponse
from services.dify_service import DifyService, DifyServiceError
from services.geoapify_service import GeoapifyService, GeoapifyServiceError
from core.errors import APIError, InputValidationError, DataProcessingError
from config import logger

router = APIRouter()

# Initialize service (these can also be injected as dependencies in a larger app)
dify_service = DifyService()
geoapify_service = GeoapifyService()

@router.post("/plan_route", response_model=GeoapifyRoutePlannerResponse, status_code=status.HTTP_200_OK)
async def plan_route(request: RouteRequest) -> JSONResponse:
    """
    Receives a natural language query, uses Dify.ai to extract structured data,
    geocodes addresses with Geoapify, and then plans an optimized route
    using Geoapify's Route Planner API.

    Args:
        request: A RouteRequest Pydantic model containing the natural language query
                 and a user ID.

    Returns:
        A JSONResponse containing the Geoapify Route Planner's GeoJSON output
        representing the optimized route.

    Raises:
        HTTPException: With appropriate status codes and details for various errors.
    """
    logger.info(f"Received route planning request for user '{request.user_id}: {request.query}'")
    
    try:
        # Step 1: Send natural language query to Dify.ai for structured data extraction
        logger.debug(f"Calling Dify.ai for query: '{request.query}'")
        dify_structured_output = await dify_service.get_route_plan_from_llm(
            user_query=request.query,
            user=request.user_id
        )
        logger.info("Successfully received structured output from Dify.ai.")
        logger.debug(f"Dify output: {dify_structured_output.model_dump_json(indent=2)}")
        
        # Step 2: Use Geoapify Service to geocode addresses and plan thr route
        logger.debug("Calling Geoapify service to plan the route.")
        geoapify_route_plan = await geoapify_service.plan_route(dify_structured_output)
        logger.info("Successfully received route plan from Geoapify")
        
        # Check for unassigned jobs/agents and provide a warning if any
        if geoapify_route_plan.unassigned_jobs_count > 0 or geoapify_route_plan.unassigned_agents_count > 0:
            warning_message = (
                f"Route plan complete with warnings: "
                f"{geoapify_route_plan.unassigned_jobs_count} jobs unassigned,"
                f"{geoapify_route_plan.unassigned_agents_count} agents unassigned."
            )
            logger.warning(warning_message)
            
        # Return the Geoapify response directly to the client
        # Use .model_dump_json() to ensure proper JSON serialization
        return JSONResponse(
            content=geoapify_route_plan.model_dump(by_alias=True, exclude_none=True),
            status_code=status.HTTP_200_OK
        )
        
    except InputValidationError as e:
        logger.error(f"Input validation error: {e.message} - Details: {e.details}")
        raise HTTPException(status_code=e.status_code, detail={"message": e.message, "details": e.details})
    except DifyServiceError as e:
        logger.error(f"Dify.ai service error: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"message": "Error from Dify.ai service", "details": str(e)})
    except GeoapifyServiceError as e:
        logger.error(f"Geoapify service error: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"message": "Error from Geoapify service", "details": str(e)})
    except DataProcessingError as e:
        logger.error(f"Data processing error: {e.message} - Details: {e.details}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"message": e.message, "details": e.details})
    except APIError as e:
        logger.error(f"Generic API error: {e.message} - Details: {e.details}")
        raise HTTPException(status_code=e.status_code, detail={"message": e.message, "details": e.details})
    except Exception as e:
        logger.exception("An unexpected internal server error occured.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"message": "An unexpected server error occurred.", "details": str(e)})