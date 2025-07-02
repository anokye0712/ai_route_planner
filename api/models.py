from pydantic import BaseModel, Field, conlist, ValidationError, RootModel, model_validator
from typing import List, Optional, Tuple, Literal, Dict, Any, Iterator

# --- Dify.ai Output Models (Expected Structured JSON from Dify.ai) ---
# These models define the structure Dify.ai is trained to output.

class TimeWindow(RootModel[Tuple[int, int]]):
    class Config:
        description = "Represents a time window as [start_seconds, end_seconds]"

    # You can add validation if needed
    def validate_time_window(self):
        start, end = self.root
        if start >= end:
            raise ValueError("Start time must be less than end time.")
        return self
    
    def __getitem__(self, item) -> int:
        return self.root[item]
    
    def iterate_time_window(self) -> Iterator[int]:
        yield from self.root
        
    def __len__(self) -> int:
        return len(self.root)
    
class AgentBreak(BaseModel):
    """Details for an agent's break"""
    duration: int = Field(..., description="Duration of the break in seconds")
    time_windows: List[TimeWindow] = Field(..., description="Time windows when the break can occur.")
        
class Agent(BaseModel):
    """Represents a vehicle or person for route planning."""
    id: str = Field(..., description="Unique identifier for the agent.")
    type: Literal["vehicle", "person", "technician"] = Field(..., description="Type of agent")
    description: Optional[str] = Field(None, description="Human-readable description of the agent.")
    capabilities: List[str] = Field(default_factory=list, 
                                    description="List of capabilities (e.g., 'large_parcel_delivery', 'HVAC_certified').")
    pickup_capacity: Optional[int] = Field(None, description="Capacity for pickups")
    delivery_capacity: Optional[int] = Field(None, description="Capacity for deliveries")
    start_address: str = Field(..., description="Starting address for the agent.")
    end_address: str = Field(..., description="Human-readable ending address (optional). If not provided, assumed to be start_address.")
    time_windows: Optional[List[TimeWindow]] = Field(None, description="Working window for the agent.")
    breaks: Optional[List[AgentBreak]] = Field(None, description="Scheduled breaks for the agent.")
    
class Job(BaseModel):
    """Represents a single job (pickup or delivery at one location)"""
    id: str = Field(..., description="Unique identifier for the job.")
    description: Optional[str] = Field(None, description="Human-readable description of the job.")
    address: str = Field(..., description="Human-readable address for the job.")
    duration: int = Field(..., description="Expected duration of the stop in seconds.")
    pickup_amount: Optional[int] = Field(None, description="Amoint to pick up")
    delivery_amount: Optional[int] = Field(None, description="Amount to deliver")
    requirements: List[str] = Field(default_factory=list,
                                    description="List of capabilities required for this job.")
    time_windows: Optional[List[TimeWindow]] = Field(None, description="Time windows when the job can be performed.")
    priority: int = Field(0, ge=0, le=100, description="Priority of the job (0-100).")
    
class ShipmentLeg(BaseModel):
    """Represents one leg (pickup or delivery) of a shipment."""
    address: str = Field(..., description="Human-readable address for the leg")
    duration: int = Field(..., description="Expected duration of the stop in seconds.")
    time_windows: Optional[List[TimeWindow]] = Field(None, description="Time windows when the leg can be performed.")
    
class Shipment(BaseModel):
    """Represents a shipment with distinct pickup and delivery points"""
    id: str = Field(..., description="Unique identifier for the shipment.")
    description: Optional[str] = Field(None, description="Human-readable description of the shipment.")
    pickup: ShipmentLeg = Field(..., description="Pickup leg for the shipment.")
    delivery: ShipmentLeg = Field(..., description="Delivery leg for the shipment.")
    amount: int = Field(..., ge=1, description="Amount of items in the shipment.")
    requirements: List[str] = Field(default_factory=list,
                                    description="List of capabilities required for this shipment.")
    priority: int = Field(0, ge=0, le=100, description="Priority of the shipment (0-100).")
    
class CommonLocation(BaseModel):
    """Represents a frequently used location (eg. depot)"""
    id: str = Field(..., description="Unique identifier for the location.")
    address: str = Field(..., description="Human-readable address for the location.")
    
class DifyRoutePlanOutput(BaseModel):
    """
    Represents the structured output expected from Dify.ai for route planning.
    This model combines all the entities (agents, jobs, shipments, common locations)
    that define a route planning problem.
    """
    mode: Literal["drive", "truck", "walk", "bicycle"] = Field(..., description="Travel mode (eg., drive, truck).")
    agents: List[Agent] = Field(default_factory=list,
                                description="List of agents (vehicles/persons) available for routing.")
    jobs: Optional[List[Job]] = Field(None,
                            description="List of individual jobs to be performed.")
    shipments: Optional[List[Shipment]] = Field(None,
                                      description="List of shipments with distinct pickup and delivery points.")
    common_locations: Optional[List[CommonLocation]] = Field(None,
                                                    description="List of frequently used locations (e.g., depots, hubs).")
    
    @model_validator(mode="after")
    def check_jobs_or_shipment(self):
        if not self.jobs and not self.shipments:
            raise ValueError("Either jobs or shipments must be provided.")
        return self
        
        
# --- API Request Model (Input to our FastAPI endpoint) ---
class RouteRequest(BaseModel):
    """"Request body for our /plan_route endpoint"""
    query: str = Field(..., min_length=10, description="Natural language query for route planning.")
    user_id: str = Field("defualt_user", description="Unique identifier for the user.")
        

# -----Geoapify API Models (for constructing requests and parsing responses) -------

# Geoapify Geocoding API Response (simplified for relevant fields)
class GeoapifyFeatureProperties(BaseModel):
    lon: float = Field(..., description="Longitude of the feature.")
    lat: float = Field(..., description="Latitude of the feature.")
    formatted: Optional[str] = Field(None, description="Formatted address of the feature.")
    country: Optional[str] = None
    city: Optional[str] = None
    
class GeoapifyFeature(BaseModel):
    properties: GeoapifyFeatureProperties
    

class GeoapifyGeocodingResponse(BaseModel):
    features: List[GeoapifyFeature]
    
# Geoapify Route Planner API Request (Partial - focusing on key elements)
# This will be constructed dynamically based on Dify.ai output.
class GeoapifyLocation(BaseModel):
    id: str
    location: Tuple[float, float] = Field(..., description="[Longitude, Latitude]")
    name: Optional[str] = None # For named locations like 'warehouse-0' or the original human-readable address
    properties: Optional[Dict[str, Any]] = None # To store original address or other info


class GeoapifyAgent(BaseModel):
    id: str
    start_location_index: int
    end_location_index: Optional[int] = None
    time_windows: Optional[List[List[int]]] = None # [[start_seconds, end_seconds]]
    breaks: Optional[List[Dict[str, Any]]] = None # e.g., [{"duration": 1800, "time_windows": [[14400, 18000]]}]
    capacities: Optional[List[float]] = None # [delivery_capacity, pickup_capacity] for multi-dimensional capacity
    capabilities: Optional[List[str]] = None
    max_travel_time: Optional[int] = None   # in seconds
    max_distance: Optional[int] = None  # in meters
    max_speed: Optional[int] = None # in KPH
  
    
class GeoapifyJob(BaseModel):
    id: str
    location_index: int
    duration: Optional[int] = None
    time_window: Optional[List[List[int]]] = None
    demands: Optional[List[float]] = None # [delivery_amount, pickup_amount] for multi-dimensional demands
    requirements: Optional[List[str]] = None
    priority: Optional[int] = None

class GeoapifyShipment(BaseModel):
    id: str
    pickup: Dict[str, Any] # location_index, duration, time_windows
    delivery: Dict[str, Any] # location_index, duration, time_windows
    demands: Optional[List[float]] = None # amount
    requirements: Optional[List[str]] = None
    priority: Optional[int] = None


class GeoapifyRoutePlannerRequest(BaseModel):
    mode: str
    locations: List[GeoapifyLocation]
    agents: List[GeoapifyAgent]
    jobs: Optional[List[GeoapifyJob]] = None
    shipments: Optional[List[GeoapifyShipment]] = None
    options: Optional[Dict[str, Any]] = None # e.g., {"traffic": "approximated", "units": "metric"}
    
# Geoapify Route Planner API Response (this will be a GeoJSON FeatureCollection)
# For simplicity, we define it as a generic Dict[str, Any] since the full GeoJSON schema is complex
# and we'll primarily pass it through.
class GeoapifyRoutePlannerResponse(BaseModel):
    # This will be a GeoJSON FeatureCollection
    type: str
    features: List[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]] = None
    properties: Optional[Dict[str, Any]] = None #To capture unassigned jobs/agents
    
    # You might want to parse specific elements if you need to extract metrics
    # e.g., total distance, travel time, unassigned jobs
    
    @property
    def unassigned_jobs_count(self) -> int:
        props = self.properties or {}
        return props.get("unassigned", {}).get("jobs_count", 0)
    
    @property
    def unassigned_agents_count(self) -> int:
        props = self.properties or {}
        return props.get("unassigned", {}).get("agents_count", 0)











if __name__ == "__main__":
    print("-----------1. Time Window Model----------")
    # -----------1. Time Window Model----------
    tw = TimeWindow.model_validate((3600, 7200))
    print(tw)  # root=(3600, 7200)

    # Access via index
    print(tw[0])  # 3600

    # Iterate
    for t in tw.iterate_time_window():
        print(t)

    # Length
    print(len(tw))  # 2

    # Invalid example (will raise error)
    try:
        tw = TimeWindow.model_validate((7200, 3600))
    except ValueError as e:
        print(e)  # Start time must be less than end time.
        
    # 2. ---------AgentBreak--------
    print("---------AgentBreak--------")
    break1 = AgentBreak(
        duration=3600,
        time_windows=[
            TimeWindow((14400, 18000)),
            TimeWindow((21600, 25200))
        ]
    )
    print(break1.model_dump_json(indent=2))
    
    # 3. ---------Agent--------
    print("---------Agent--------")
    agent = Agent(#type:ignore
        id="refrigerated_truck_01",
        type="vehicle",
        description="Refrigerated Truck",
        capabilities=["cold_chain_delivery"],
        delivery_capacity=8,
        start_address="Cold Storage Facility, 50 Pandan Loop, Singapore",
        end_address="Cold Storage Facility, 50 Pandan Loop, Singapore",
        time_windows=[
            TimeWindow((14400, 18000)),
        ],
        breaks=[
            AgentBreak(
                duration=3600,
                time_windows=[
                    TimeWindow((14400, 18000)),
                ]
            )
        ]
    )
    print(agent.model_dump_json(indent=2))
    
    # 4. -------------Job-------------
    print("-------------Job-------------")
    job = Job(# type:ignore
        id="delivery_suntec",
        description="General delivery to Suntec",
        address="Suntec City Tower 4, Singapore",
        duration=600,  # 10 minutes
        delivery_amount=5,
        requirements=["general_delivery"],
        time_windows=[
            TimeWindow((0, 14400))  # Available before 4 hours (0 - 4am)
        ],
        priority=75
    )

    print(job.model_dump_json(indent=2))
    
    # 5. ---------Shipment Leg--------
    print("---------Shipment Leg--------")
    pickup_leg = ShipmentLeg(#type:ignore
        address="Changi Business Park, Singapore",
        duration=1200,  # 20 minutes
        time_windows=[
            TimeWindow((0, 28800))  # Available before 8am
        ]
    )

    print(pickup_leg.model_dump_json(indent=2))
    
    # 6. ----------Shipment---------
    print("---------Shipment---------")
    shipment = Shipment(#type:ignore
        id="pickup_changi_bp",
        description="Pickup from Changi Business Park and deliver to Main Logistics Hub",
        pickup=ShipmentLeg(#type:ignore
            address="Changi Business Park, Singapore",
            duration=1200,
            time_windows=[
                TimeWindow((0, 28800))  # Available before 8am
            ]
        ),
        delivery=ShipmentLeg(#type: ignore
            address="Main Logistics Hub, 10 Tuas South Ave 1, Singapore",
            duration=600,
            time_windows=[
                TimeWindow((3600, 39600)),  # From 1am to 11am
                TimeWindow((43200, 50400))   # From 12pm to 2pm
            ]
        ),
        amount=7,
        requirements=["general_delivery"],
        priority=85
    )

    print(shipment.model_dump_json(indent=2))
    
    # 7. ----------Common Location--------
    print("---------Common Location--------")
    main_warehouse = CommonLocation(
        id="main_logistics_hub",
        address="Main Logistics Hub, 10 Tuas South Ave 1, Singapore"
    )

    print(main_warehouse.model_dump_json(indent=2))
    
    # 8. ----------DifyRoutePlanOutput--------
    print("---------DifyRoutePlanOutput--------")
    plan = DifyRoutePlanOutput(
        mode="truck",
        agents=[agent],  # From earlier Agent example
        jobs=[job],  # From Job example
        shipments=[shipment],  # From Shipment example
        common_locations=[
            CommonLocation(id="main_logistics_hub", address="Main Logistics Hub, 10 Tuas South Ave 1, Singapore"),
            CommonLocation(id="satellite_depot", address="Satellite Depot, 20 Tuas West Road, Singapore")
        ]
    )

    print(plan.model_dump_json(indent=2))
    
    # 9. ------------RouteRequest----------
    print("---------RouteRequest----------")
    request = RouteRequest(
        query="Plan delivery routes for 3 trucks starting from the west depot. "
            "Deliver 5 packages to Clementi Mall before 4am and 8 to Jurong Point by 6am.",
        user_id="user_12345"
    )

    print(request.model_dump_json(indent=2))
    
    # 10. --------GeoapidyFeatureProperties---------
    print("---------GeoapidyFeatureProperties---------")
    geo_data = GeoapifyFeatureProperties(
        lon=103.8585,
        lat=1.2833,
        formatted="Singapore",
        country="Singapore",
        city="Singapore"
    )

    print(geo_data.model_dump_json(indent=2))
    
    # 11. -----------GeapifyFeature--------
    print("---------GeapifyFeature--------")
    
    feature = GeoapifyFeature(
        properties= geo_data
    )

    print(feature.model_dump_json(indent=2))
    
    # 12. ----------GeoapifyGeocodingResponse--------
    print("----------GeoapifyGeocodingResponse--------")
    featureList = GeoapifyGeocodingResponse(
        features=[feature]
    )
    print(featureList.model_dump_json(indent=2))
    
    
    # 13. ----------Geoapify Locataion---------------
    print("-------------Geoapify Location-------------")
    clementi_location = GeoapifyLocation(
        id="clementi_mall",
        location=(103.7546, 1.3358),  # Lon, Lat
        name="Clementi Mall, Singapore",
        properties={
            "address": "Clementi MRT, Singapore",
            "type": "commercial"
        }
    )

    print(clementi_location.model_dump_json(indent=2))
    
    # 14. -----------Geoapify Agent---------------
    print("----------Geoapify Agent-----------")
    agent = GeoapifyAgent(
        id="refrigerated_truck_01",
        start_location_index=0,
        end_location_index=0,
        time_windows=[[3600, 36000]],  # 1am - 10am
        breaks=[
            {
                "duration": 1800,
                "time_windows": [[14400, 18000]]  # 4am - 5am
            }
        ],
        capacities=[8, 0],  # delivery_capacity = 8, pickup_capacity = 0
        capabilities=["cold_chain_delivery"],
        max_travel_time=36000,
        max_distance=50000,
        max_speed=60
    )

    print(agent.model_dump_json(indent=2))
    
    
    #15. -------------Geoapify Job-------------
    print("--------Geoapify job-----------")
    job = GeoapifyJob(
        id="delivery_suntec",
        location_index=1,
        duration=600,  # 10 minutes
        time_window=[[0, 14400]],  # Available before 4 hours (0 - 4am)
        demands=[5, 0],  # delivery_amount = 5, pickup_amount = 0
        requirements=["general_delivery"],
        priority=75
    )

    print(job.model_dump_json(indent=2))
    
    #. 16 ------------Geoapify Shipment----------
    print("-----------Geoapify Shipment---------")
    shipment = GeoapifyShipment(
        id="pickup_changi_bp",
        pickup={
            "location_index": 1,
            "duration": 1200,
            "time_windows": [[0, 28800]]  # Available before 8am
        },
        delivery={
            "location_index": 0,
            "duration": 600,
            "time_windows": [[3600, 39600], [43200, 50400]]  # Two possible time slots
        },
        demands=[7.0, 0.0],
        requirements=["general_delivery"],
        priority=85
    )

    print(shipment.model_dump_json(indent=2))
    
    
    # 17. ----------GeoapifyRoutePlannerRequest-----------
    print("--------GeoapifyRutePlannerRequest----------")
    request = GeoapifyRoutePlannerRequest(
        mode="truck",
        locations=[
            GeoapifyLocation(id="main_hub", location=(103.8585, 1.2833), name="Main Logistics Hub"),
            GeoapifyLocation(id="clementi_mall", location=(103.7546, 1.3358), name="Clementi Mall")
        ],
        agents=[
            GeoapifyAgent(
                id="refrigerated_truck_01",
                start_location_index=0,
                capacities=[8, 0],
                capabilities=["cold_chain_delivery"],
                max_travel_time=36000
            )
        ],
        jobs=[
            GeoapifyJob(
                id="delivery_suntec",
                location_index=1,
                duration=600,
                time_window=[[0, 14400]],
                demands=[5, 0],
                requirements=["general_delivery"],
                priority=75
            )
        ],
        shipments=[
            GeoapifyShipment(
                id="pickup_changi_bp",
                pickup={
                    "location_index": 1,
                    "duration": 1200,
                    "time_windows": [[0, 8800]]
                },
                delivery={
                    "location_index": 0,
                    "duration": 600,
                    "time_windows": [[3600, 39600]]
                },
                demands=[7, 0],
                requirements=["general_delivery"],
                priority=85
            )
        ],
        options={"traffic": "approximated", "units": "metric"}
    )

    print(request.model_dump_json(indent=2))
    
    
    # 18. ------------GeoapifyRoutePlannerResponse-----------
    print("-----------GeoapifyRoutePlannerResponse----------")
    response_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[103.8585, 1.2833], [103.7546, 1.3358]]
                },
                "properties": {
                    "agent_id": "refrigerated_truck_01",
                    "job_ids": ["delivery_suntec"],
                    "total_time": 3600,
                    "distance_meters": 12000
                }
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [103.7546, 1.3358]
                },
                "properties": {
                    "job_id": "delivery_suntec",
                    "stop_type": "delivery",
                    "arrival": "14400s",
                    "departure": "15000s"
                }
            }
        ],
        "metadata": {
            "total_time": 3600,
            "total_distance": 12000,
        },
        "properties": {
            "unassigned": {
                "jobs_count": 1,
                "agents_count": 0
            }
        }
    }
    route_response = GeoapifyRoutePlannerResponse(**response_data)

    print(f"Total Distance: {route_response.metadata.get("total_time")} meters") #type:ignore
    print(f"Total Time: {route_response.metadata.get("total_distance")} seconds") #type: ignore
    print(f"Unassigned Jobs: {route_response.unassigned_jobs_count}")
    print(f"Unassigned Agents: {route_response.unassigned_agents_count}")