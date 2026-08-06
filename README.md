# AI Career Coach App

## Overview

The AI Career Coach application is an AI-powered platform that matches user resumes and skills with relevant career opportunities using semantic search pipelines, vector databases, and AI-powered recommendations.

---

# Project Structure

```
backend/        # Backend APIs and business logic
streamlit_app/  # Streamlit user interface
frontend/       # Frontend resources (if applicable)
docs/           # Project documentation
data/           # Sample data and resources
```

---

# Local Development Setup

## 1. Clone the Repository

```bash
git clone https://github.com/MoHatemTC/ai-career-coach-app.git
cd ai-career-coach-app
```

---

## 2. Create a Virtual Environment

```bash
python -m venv venv
```

### Windows

```bash
venv\Scripts\activate
```

### macOS / Linux

```bash
source venv/bin/activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Configure Environment Variables

Create a `.env` file from `.env.example`.

### Windows

```powershell
copy .env.example .env
```

### macOS / Linux

```bash
cp .env.example .env
```

Update the required environment variables (API keys and configuration values) before running the application.

---

## 5. Run the Backend

```bash
uvicorn backend.main:app --reload
```

---

# Running with Docker

## Prerequisites

- Docker Desktop
- Docker Compose

---

## 1. Clone the Repository

```bash
git clone https://://github.com/MoHatemTC/ai-career-coach-app.git
cd ai-career-coach-app
```

---

## 2. Create the Environment File

### Windows

```powershell
copy .env.example .env
```

### macOS / Linux

```bash
cp .env.example .env
```

Update the required environment variables before starting the containers.

---

## 3. Build and Start the Containers

```bash
docker compose up --build
```

To run the application in detached mode:

```bash
docker compose up -d
```

---

## Stop the Containers

```bash
docker compose down
```

---

# Available Services

| Service | URL |
|----------|-----|
| Streamlit UI | http://localhost:8501 |
| Backend API | http://localhost:8000 |
| Qdrant Dashboard | http://localhost:6333/dashboard |

---

# Documentation

Additional documentation can be found in the `docs/` directory, including:

- Backend Architecture
- API Design
- System Documentation

---

# Notes

- Ensure Docker Desktop is running before executing Docker Compose commands.
- Create a valid `.env` file from `.env.example`.
- The Docker Compose configuration includes the Backend, Streamlit, and Qdrant services.
