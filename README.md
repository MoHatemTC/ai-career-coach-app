# AI Career Coach App

## Overview
The Career Coach application is an AI-powered platform designed to match user resumes and skills with relevant career opportunities using advanced semantic search pipelines and vector databases. It replaces traditional keyword filtering with deep semantic understanding to provide accurate, curated job matches.

## Project Structure
* `backend/`: Contains the core backend logic, API services, features, and vector retrieval pipelines (including Qdrant integration).
* `frontend/`: Contains the user interface components and user interaction layers.
* `docs/`: Contains system architecture documents and technical specifications (including `backend_architecture.md`).

## Prerequisites
* Python 3.9 or higher
* Pip package manager

## Setup & Installation Guide

1. **Clone the Repository:**
   ```bash
   git clone [https://github.com/MoHatemTC/ai-career-coach-app.git](https://github.com/MoHatemTC/ai-career-coach-app.git)
   cd ai-career-coach-app 
   Install Dependencies:

Bash
pip install -r requirements.txt
Configure Environment Variables:

Create a .env file in the root directory based on .env.example and add your required configuration keys (such as Qdrant or API keys).

Run the Application:

Bash
uvicorn backend.main:app --reload
Documentation
For detailed system architecture and API contracts, please refer to the Backend Architecture Document.