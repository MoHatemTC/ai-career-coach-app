# Architecture

This repository is divided into simple learning areas.

## Backend

The backend is responsible for:

- Receiving CV uploads.
- Reading and parsing CV text.
- Fetching or loading job data.
- Matching jobs to user profiles.
- Calling the AI provider through one shared client.
- Generating skill gaps and application materials.

Recommended folders:

- `backend/routes/` - API endpoints.
- `backend/services/` - business logic.
- `backend/models/` - data structures and database models.
- `backend/prompts/` - AI prompt templates.
- `backend/tests/` - backend tests.

## Frontend

The frontend is responsible for:

- Uploading CVs.
- Showing profile information.
- Showing job matches.
- Showing skill gaps.
- Letting users review generated material.

Recommended folders:

- `frontend/src/pages/` - full screens.
- `frontend/src/components/` - reusable UI pieces.
- `frontend/src/api/` - backend API calls.

## AI Prompt Flow

Prompts should not be hard-coded inside service files.

Expected flow:

1. A service loads a prompt from `backend/prompts/`.
2. The service sends user/profile/job data to the AI client.
3. The AI client returns a structured response.
4. The service validates the response before returning it to the route.

## Data Flow

Basic product flow:

1. User uploads a CV.
2. Backend extracts profile information.
3. Backend loads jobs from sample data or an API.
4. Matching service ranks jobs.
5. Skill gap service identifies missing skills.
6. Generator service creates reviewed application drafts.
