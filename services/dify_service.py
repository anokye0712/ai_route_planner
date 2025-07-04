import httpx
import os
import re
import json
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type, wait_exponential
from typing import Dict, Any, Optional

from api.models import DifyRoutePlanOutput
from config import settings


class DifyServiceError(Exception):
    """Custom exception for Dify service-related errors."""
    pass


class DifyService:
    def __init__(self):
        self.api_key: str = settings.DIFY_API_KEY
        self.base_url: str = settings.DIFY_API_BASE_URL
        self.app_id: str = settings.APP_ID
        self.chat_messages_endpoint: str = f"{self.base_url}/chat-messages"
        
        if not self.api_key:
            raise ValueError("DIFY_API_KEY environment variable not set.")
        if not self.app_id:
            raise ValueError("DIFY_APP_ID environment variable not set.")
        
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError) | retry_if_exception_type(DifyServiceError),
        reraise=True # Re-raise the last exception if all retries fail
    )
    async def get_route_plan_from_llm(self, user_query: str, user: str) -> DifyRoutePlanOutput:
        """
        Sends a natural language query to Dify.ai and expects a structured JSON output.
        Args:
            user_query: The natural language request for route planning.
            user: A unique identifier for the user (for Dify's conversation tracking).

        Returns:
            A Pydantic model representing the structured route plan from Dify.ai.

        Raises:
            DifyServiceError: If the Dify.ai API returns an error or unexpected response.
            httpx.RequestError: For network-related issues.
            ValueError: If Dify.ai's response cannot be parsed into the expected Pydantic model.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": {},
            "query": user_query,
            "response_mode": "blocking",
            "user": user,
            "conversation_id": None
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.chat_messages_endpoint, headers=headers, json=payload, timeout=60.0) # Increased timeout
                response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx responses
                
                response_data = response.json()
                
                # Dify's chat-messages API returns a structure like:
                # { "answer": "...", "created_at": ..., "conversation_id": ..., "id": ..., "message_from": ..., "message_id": ..., "message_type": ..., "metadata": { "usage": {...} }, "status": "success" }
                # The actual structured JSON output we configured Dify to produce will be *inside* the "answer" field.
                
                llm_answer_text = response_data.get("answer")
                if not llm_answer_text:
                    raise DifyServiceError(f"Dify.ai response missing 'answer' field. Full response: {response_data}")
                
                # This regex removes optional leading ```json or ```JSON, and trims trailing ```
                cleaned_answer = re.sub(r'^\s*```(?:json|JSON)?\s*', '', llm_answer_text).rstrip('`')

                
                # Attempt to parse the 'answer' field as JSON
                # The LLM is instructed to output JSON, so we expect it to be a valid JSON string
                try:
                    structured_output = json.loads(cleaned_answer)
                except json.JSONDecodeError as e:
                    raise DifyServiceError(f"Dify.ai 'answer' field is not valid JSON: {llm_answer_text[:500]}... Error: {e}")
                
                # Validate the parsed JSON against our Pydantic Model
                return DifyRoutePlanOutput(**structured_output)
            
            except httpx.HTTPStatusError as e:
                # This handles 4xx/5xx responses from Dify.ai
                error_details = e.response.text
                raise DifyServiceError(f"Dify.ai API returned HTTP error {e.response.status_code}: {error_details}") from e
            except httpx.RequestError as e:
                # This handles network errors, timeouts, etc.
                raise httpx.RequestError(f"Network error communicating with Dify.ai: {e}") from e
            except ValueError as e:
                # This handles Pydantic validation errors
                raise DifyServiceError(f"Failed to parse Dify.ai output into Pydantic model: {e}") from e
            except Exception as e:
                # Catch any other unexpected errors
                raise DifyServiceError(f"An unexpected error occurred with Dify.ai service: {e}") from e




if __name__ == "__main__":
    import asyncio
    import json
    from services.geoapify_service import GeoapifyService
    
    service = DifyService()

    async def test():
        try:
            result = await service.get_route_plan_from_llm(
                user_query="""
                I need to plan a route for three delivery agents: Alpha, Bravo, and Charlie. All agents start and end their shifts at a depot in Parliament Square, Westminster, London SW1P 3PA, UK.

Agent Alpha works from 8 AM to 5 PM.
Agent Bravo works from 9 AM to 6 PM, and can handle fragile items.
Agent Charlie works from 10 AM to 7 PM, and can handle cold chain deliveries.

I have three shipments to deliver:

Alpha Shipment: Pick up at Euston Road, London NW1 2RA, UK, taking 15 minutes, with a pickup window between 8 AM and 11 AM. Deliver to Victoria Street, London SW1E 5JE, UK, taking 10 minutes, with a delivery window between 8 AM and 1 PM.

Bravo Shipment: Pick up at High Holborn, London WC1V 6PX, UK, taking 20 minutes, with a pickup window between 10 AM and 12 PM. This shipment contains fragile items. Deliver to Buckingham Palace Road, London SW1W 0PP, UK, taking 10 minutes, with a delivery window between 10 AM and 3 PM.

Charlie Shipment: Pick up at Long Acre, London WC2E 9EZ, UK, taking 15 minutes, with a pickup window between 11 AM and 1 PM. This shipment requires cold chain delivery. Deliver to The Strand, London WC2N 5DN, UK, taking 10 minutes, with a delivery window between 11 AM and 4 PM.

The travel mode should be 'drive', using approximated traffic data and metric units.
                """,
                user="test_user_123"
            )

            geoapify_service = GeoapifyService()

            final_res = await geoapify_service.plan_route(result)
            print("Final response object:")
            #print(final_res.model_dump_json(indent=2)) # Print the JSON string for inspection

            with open("route_plan_result.json", "w", encoding="utf-8") as f:
                # model_dump() returns a dictionary, which json.dump can directly handle.
                # If you use model_dump_json(), it returns a JSON string, which you'd need to parse first.
                json.dump(final_res.model_dump(), f, indent=4, ensure_ascii=False)
            print("\nSuccessfully saved route plan to route_plan_result.json")

        except DifyServiceError as e:
            print("❌ DifyServiceError:", e)
        except Exception as e:
            print("⚠️ Unexpected error:", e)


    asyncio.run(test())   