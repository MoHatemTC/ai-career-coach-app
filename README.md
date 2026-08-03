# AI Career Coach App

## Overview
The Career Coach application is an AI-powered platform designed to match user resumes and skills with relevant career opportunities using advanced semantic search pipelines and vector databases. 

## Project Structure
* `backend/`: Contains the core backend logic, API services, and vector retrieval pipelines.
* `frontend/`: Contains the user interface components.
* `docs/`: Contains system architecture documents (including `backend_architecture.md`).

## Environment Setup & Installation Guide

Follow these explicit step-by-step instructions to set up the environment, install dependencies, and start the application locally:

### 1. Environment Setup
Clone the repository and set up a virtual environment to isolate the project dependencies.

```bash
git clone [https://github.com/MoHatemTC/ai-career-coach-app.git](https://github.com/MoHatemTC/ai-career-coach-app.git)
cd ai-career-coach-app

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
2. Dependency Installation
Once the virtual environment is activated, install all required packages using pip.

Bash
pip install -r requirements.txt
3. Startup Commands
After configuring your environment variables (using a .env file), run the backend application using Uvicorn.

Bash
uvicorn backend.main:app --reload
Documentation
For detailed system architecture, parameter types, request payloads, and API contracts, please refer to the Backend Architecture Document.