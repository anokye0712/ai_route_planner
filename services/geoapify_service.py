import httpx
import os
import json
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type, wait_exponential
from typing import List, Tuple, Dict, Any, Set, Optional

from api.models import (
    GeoapifyGeocodingResponse,
    GeoapifyRoutePlannerRequest,
    GeoapifyRoutePlannerResponse,
    GeoapifyLocation,
    DifyRoutePlanOutput,
    Agent as DifyAgent,
    Job as DifyJob,
    Shipment as DifyShipment,
    CommonLocation as DifyCommonLocation,
    TimeWindow as DifyTimeWindow,
    GeoapifyAgent,
    GeoapifyJob,
    GeoapifyShipment
)
from config import settings

class GeoapifyServiceError(Exception):
    """Custom exception for Geoapify service-related errors."""
    pass


class GeoapifyService:
    def __init__(self):
        self.api_key: str = settings.GEOAPIFY_API_KEY
        self.geocoding_base_url: str = settings.geoapify_geocoding_url
        self.route_planner_base_url: str = settings.geoapify_route_planner_url
        self.routing_base_url: str = settings.geoapify_routing_url


        if not self.api_key:
            raise ValueError("GEOAPIFY_API_KEY environment variable not set.")

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError) | retry_if_exception_type(GeoapifyServiceError),
        reraise=True
    )
    async def geocode_address(self, address: str) -> Tuple[float, float]:
        """
        Converts a human-readable address to geographic coordinates (longitude, latitude).
        Args:
            address: The human-readable address string.

        Returns:
            A tuple (longitude, latitude).

        Raises:
            GeoapifyServiceError: If geocoding fails or no coordinates are found.
        """
        params = {
            "text": address,
            "apiKey": self.api_key,
            "limit": 1 # We usually only need the top, most confident result
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.geocoding_base_url}/search", params=params, timeout=10.0)
                response.raise_for_status()
                geocoding_data = GeoapifyGeocodingResponse(**response.json())

                if not geocoding_data.features:
                    raise GeoapifyServiceError(f"No coordinates found for address: '{address}'.")

                # Geoapify returns [lon, lat] in properties
                lon = geocoding_data.features[0].properties.lon
                lat = geocoding_data.features[0].properties.lat
                return (lon, lat)

            except httpx.HTTPStatusError as e:
                raise GeoapifyServiceError(f"Geoapify Geocoding API returned HTTP error {e.response.status_code}: {e.response.text}") from e
            except httpx.RequestError as e:
                raise httpx.RequestError(f"Network error communicating with Geoapify Geocoding API: {e}") from e
            except Exception as e:
                raise GeoapifyServiceError(f"An unexpected error occurred during geocoding for '{address}': {e}") from e


    async def geocode_addresses_batch(self, addresses: Set[str]) -> Dict[str, Tuple[float, float]]:
        """
        Geocodes a batch of unique addresses.
        Args:
            addresses: A set of unique human-readable address strings.

        Returns:
            A dictionary mapping original address strings to their (longitude, latitude) coordinates.
        """
        geocoded_results: Dict[str, Tuple[float, float]] = {}
        for address in addresses:
            try:
                coords = await self.geocode_address(address)
                geocoded_results[address] = coords
            except GeoapifyServiceError as e:
                print(f"Warning: Could not geocode address '{address}'. Skipping. Error: {e}")
            except httpx.RequestError as e:
                print(f"Warning: Network error geocoding address '{address}'. Skipping. Error: {e}")
        return geocoded_results

    def _prepare_geoapify_time_windows(self, time_windows: Optional[List[DifyTimeWindow]]) -> Optional[List[List[int]]]:
        """Converts Dify time windows (Pydantic objects) to Geoapify's expected format (list of lists of ints)."""
        if not time_windows:
            return None
        return [list(tw.root) for tw in time_windows]

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError) | retry_if_exception_type(GeoapifyServiceError),
        reraise=True
    )
    async def _get_detailed_route_geometry(self, waypoints: List[Tuple[float, float]], mode: str) -> Dict[str, Any]:
        """
        Calls the Geoapify Routing API to get detailed road-following geometry.
        Args:
            waypoints: A list of (longitude, latitude) tuples in order.
            mode: The travel mode (e.g., "drive", "walk").

        Returns:
            A GeoJSON LineString or MultiLineString geometry object.
        """
        if len(waypoints) < 2:
            return {"type": "LineString", "coordinates": []} # Or MultiLineString with empty array

        waypoints_str = "|".join([f"lonlat:{lon},{lat}" for lon, lat in waypoints])
        params = {
            "waypoints": waypoints_str,
            "mode": mode,
            "apiKey": self.api_key,
            "details": "route_details", # Request detailed geometry
            "format": "geojson" # Ensure GeoJSON output
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.routing_base_url, params=params, timeout=30.0)
                response.raise_for_status()
                routing_data = response.json()

                if routing_data and routing_data.get("features"):
                    # The Routing API returns a FeatureCollection. We want the geometry of the first feature.
                    return routing_data["features"][0]["geometry"]
                else:
                    print(f"Warning: No detailed route geometry found for waypoints: {waypoints}")
                    return {"type": "LineString", "coordinates": []} # Default to empty geometry

            except httpx.HTTPStatusError as e:
                print(f"Error fetching detailed route geometry (HTTP {e.response.status_code}): {e.response.text}")
                return {"type": "LineString", "coordinates": []}
            except httpx.RequestError as e:
                print(f"Network error fetching detailed route geometry: {e}")
                return {"type": "LineString", "coordinates": []}
            except Exception as e:
                print(f"Unexpected error fetching detailed route geometry: {e}")
                return {"type": "LineString", "coordinates": []}


    async def plan_route(self, dify_output: DifyRoutePlanOutput) -> GeoapifyRoutePlannerResponse:
        """
        Takes the Dify.ai structured output, geocodes addresses, and then plans an optimized route
        using Geoapify's Route Planner API. Finally, it fetches detailed road-following geometry
        for each agent's route using the Geoapify Routing API.

        Args:
            dify_output: The Pydantic model representing Dify.ai's route plan output.

        Returns:
            A Pydantic model representing the Geoapify Route Planner API response (GeoJSON),
            with updated detailed geometries.

        Raises:
            GeoapifyServiceError: If routing fails or a critical address cannot be geocoded.
        """
        all_addresses_to_geocode: Set[str] = set()

        # Collect all unique addresses from Dify.ai output
        for agent in dify_output.agents:
            all_addresses_to_geocode.add(agent.start_address)
            if agent.end_address:
                all_addresses_to_geocode.add(agent.end_address)
        if dify_output.jobs:
            for job in dify_output.jobs:
                all_addresses_to_geocode.add(job.address)
        if dify_output.shipments:
            for shipment in dify_output.shipments:
                all_addresses_to_geocode.add(shipment.pickup.address)
                all_addresses_to_geocode.add(shipment.delivery.address)
        if dify_output.common_locations:
            for loc in dify_output.common_locations:
                all_addresses_to_geocode.add(loc.address)

        # Geocode all collected addresses in a batch (conceptually)
        geocoded_map: Dict[str, Tuple[float, float]] = await self.geocode_addresses_batch(all_addresses_to_geocode)

        geo_locations: List[GeoapifyLocation] = []
        geo_agents_payload: List[GeoapifyAgent] = []
        geo_jobs_payload: List[GeoapifyJob] = []
        geo_shipments_payload: List[GeoapifyShipment] = []

        address_to_location_index: Dict[str, int] = {}
        coords_to_location_index: Dict[Tuple[float, float], int] = {}

        location_id_counter = 0
        for address_str in all_addresses_to_geocode:
            coords = geocoded_map.get(address_str)
            if coords:
                if coords in coords_to_location_index:
                    address_to_location_index[address_str] = coords_to_location_index[coords]
                else:
                    location_id = f"loc-{location_id_counter}"
                    geo_location = GeoapifyLocation(
                        id=location_id,
                        location=coords,
                        name=address_str,
                        properties={"original_address": address_str}
                    )
                    geo_locations.append(geo_location)
                    current_index = len(geo_locations) - 1
                    address_to_location_index[address_str] = current_index
                    coords_to_location_index[coords] = current_index
                    location_id_counter += 1
            else:
                print(f"Warning: Address '{address_str}' was not geocoded and will be skipped in routing.")


        # 2. Convert Dify Agents to Geoapify Agents
        for agent in dify_output.agents:
            start_idx = address_to_location_index.get(agent.start_address)
            end_idx = address_to_location_index.get(agent.end_address) if agent.end_address else start_idx

            if start_idx is None:
                raise GeoapifyServiceError(f"Start address '{agent.start_address}' for agent '{agent.id}' could not be geocoded.")

            agent_data = {
                "id": agent.id,
                "start_location_index": start_idx,
                "end_location_index": end_idx,
            }
            if agent.time_windows:
                agent_data["time_windows"] = self._prepare_geoapify_time_windows(agent.time_windows)
            if agent.breaks:
                agent_data["breaks"] = [
                    {
                        "duration": b.duration,
                        "time_windows": self._prepare_geoapify_time_windows(b.time_windows)
                    } for b in agent.breaks
                ]
            capacities = []
            if agent.delivery_capacity is not None:
                capacities.append(float(agent.delivery_capacity))
            if agent.pickup_capacity is not None:
                if len(capacities) == 0:
                    capacities.append(float(agent.pickup_capacity))
                else:
                    capacities.append(float(agent.pickup_capacity))

            if capacities:
                 agent_data["capacities"] = capacities

            if agent.capabilities:
                agent_data["capabilities"] = agent.capabilities

            geo_agents_payload.append(GeoapifyAgent(**agent_data))

        # 3. Convert Dify Jobs to Geoapify Jobs
        if dify_output.jobs:
            for job in dify_output.jobs:
                job_loc_idx = address_to_location_index.get(job.address)
                if job_loc_idx is None:
                    print(f"Warning: Job address '{job.address}' for job '{job.id}' could not be geocoded. Skipping job.")
                    continue

                job_data = {
                    "id": job.id,
                    "location_index": job_loc_idx,
                    "duration": job.duration,
                }
                if job.time_windows:
                    job_data["time_windows"] = self._prepare_geoapify_time_windows(job.time_windows)
                demands = []
                if job.delivery_amount is not None:
                    demands.append(float(job.delivery_amount))
                if job.pickup_amount is not None:
                    if len(demands) == 0:
                        demands.append(float(job.pickup_amount))
                    else:
                        demands.append(float(job.pickup_amount))
                if demands:
                    job_data["demands"] = demands
                if job.requirements:
                    job_data["requirements"] = job.requirements
                if job.priority is not None:
                    job_data["priority"] = job.priority

                geo_jobs_payload.append(GeoapifyJob(**job_data))

        # 4. Convert Dify Shipments to Geoapify Shipments
        if dify_output.shipments:
            for shipment in dify_output.shipments:
                pickup_loc_idx = address_to_location_index.get(shipment.pickup.address)
                delivery_loc_idx = address_to_location_index.get(shipment.delivery.address)

                if pickup_loc_idx is None or delivery_loc_idx is None:
                    print(f"Warning: Shipment '{shipment.id}' has ungeocodeable pickup/delivery address. Skipping shipment.")
                    continue

                shipment_data = {
                    "id": shipment.id,
                    "pickup": {
                        "location_index": pickup_loc_idx,
                        "duration": shipment.pickup.duration,
                    },
                    "delivery": {
                        "location_index": delivery_loc_idx,
                        "duration": shipment.delivery.duration,
                    }
                }
                if shipment.pickup.time_windows:
                    shipment_data["pickup"]["time_windows"] = self._prepare_geoapify_time_windows(shipment.pickup.time_windows)
                if shipment.delivery.time_windows:
                    shipment_data["delivery"]["time_windows"] = self._prepare_geoapify_time_windows(shipment.delivery.time_windows)

                if shipment.amount is not None:
                    shipment_data["demands"] = [float(shipment.amount)]
                if shipment.requirements:
                    shipment_data["requirements"] = shipment.requirements
                if shipment.priority is not None:
                    shipment_data["priority"] = shipment.priority

                geo_shipments_payload.append(GeoapifyShipment(**shipment_data))

        # Ensure there are locations to route, otherwise Geoapify will fail
        if not geo_locations:
            raise GeoapifyServiceError("No valid geocoded locations found to create a route plan.")
        if not geo_agents_payload:
            raise GeoapifyServiceError("No valid agents found for route planning.")
        if not geo_jobs_payload and not geo_shipments_payload:
            raise GeoapifyServiceError("No valid jobs or shipments found for route planning.")

        # Construct the initial Geoapify Route Planner Request
        route_planner_request = GeoapifyRoutePlannerRequest(
            mode=dify_output.mode,
            locations=geo_locations,
            agents=geo_agents_payload,
            jobs=geo_jobs_payload if geo_jobs_payload else None,
            shipments=geo_shipments_payload if geo_shipments_payload else None,
            # Removed "details" here as it doesn't seem to work for detailed geometry in Route Planner API
            options={
                "traffic": "approximated",
                "units": "metric"
            }
        )

        async with httpx.AsyncClient() as client:
            try:
                request_payload = route_planner_request.model_dump(by_alias=True, exclude_none=True)
                response = await client.post(
                    self.route_planner_base_url,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    params={"apiKey": self.api_key},
                    json=request_payload,
                    timeout=120.0
                )
                response.raise_for_status()

                # This is the GeoJSON FeatureCollection from the Route Planner
                geoapify_route_planner_response_data = response.json()
                geoapify_route_plan_response = GeoapifyRoutePlannerResponse(**geoapify_route_planner_response_data)

                # --- NEW: Fetch detailed geometries for each agent's route ---
                updated_features = []
                for feature in geoapify_route_plan_response.features:
                    # Extract waypoints from the planned route for this agent
                    # The 'waypoints' array in the feature properties contains the ordered stops
                    agent_waypoints_data = feature.get('properties', {}).get('waypoints', [])
                    
                    # Convert waypoint data to (lon, lat) tuples
                    # Ensure we use the 'location' field which is the matched coordinate
                    ordered_coords_for_routing = [
                        tuple(wp['location']) for wp in agent_waypoints_data if 'location' in wp
                    ]

                    if ordered_coords_for_routing:
                        # Fetch detailed geometry for this sequence of waypoints
                        detailed_geometry = await self._get_detailed_route_geometry(
                            waypoints=ordered_coords_for_routing,
                            mode=dify_output.mode # Use the overall mode for routing
                        )
                        # Update the feature's geometry with the detailed one
                        feature['geometry'] = detailed_geometry
                    updated_features.append(feature)
                
                # Update the GeoapifyRoutePlannerResponse with the new features
                geoapify_route_plan_response.features = updated_features

                return geoapify_route_plan_response

            except httpx.HTTPStatusError as e:
                error_detail = e.response.text
                raise GeoapifyServiceError(f"Geoapify Route Planner API returned HTTP error {e.response.status_code}: {error_detail}") from e
            except httpx.RequestError as e:
                raise httpx.RequestError(f"Network error communicating with Geoapify Route Planner API: {e}") from e
            except Exception as e:
                raise GeoapifyServiceError(f"An unexpected error occurred during route planning with Geoapify: {e}") from e
