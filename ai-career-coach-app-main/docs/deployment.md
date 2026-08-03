# Deployment Guide

Deployment is not implemented yet. This document should be updated as the project grows.

## Initial Goal

The first deployment goal is local Docker Compose:

- Backend API container.
- Frontend container.
- Optional database container if the team moves from SQLite to PostgreSQL.

## Rules

- Do not put secrets in Dockerfiles or compose files.
- Use `.env` locally and platform secrets in hosted environments.
- Keep deployment steps repeatable.
- Update this document whenever deployment commands change.
