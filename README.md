# AI Route Planner

## Overview
AI Route Planner is a FastAPI-based backend application designed to optimize delivery and pickup routes using natural language commands. It integrates Dify.ai and Geoapify for intelligent route planning.

## Features
- Natural language-based route optimization.
- Integration with Dify.ai for AI-powered decision-making.
- Integration with Geoapify for geospatial data and mapping.
- RESTful API endpoints for seamless integration.

## Installation
1. Clone the repository:
   ```bash
   git clone <repository-url>
   ```
2. Navigate to the project directory:
   ```bash
   cd ai_route_planner
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage
1. Run the application:
   ```bash
   uvicorn main:app --reload
   ```
2. Access the API documentation at:
   - Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
   - Redoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## API Endpoints
- `/api/v1/`: Main API endpoints for route planning.
- `/`: Root endpoint with a welcome message.

## License
This project is licensed under the MIT License.