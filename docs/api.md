# API Documentation

API endpoints should be documented here as they are created.

For each endpoint, include:

- Method and path.
- Purpose.
- Request body example.
- Response example.
- Error cases.

## Example Format

```txt
POST /cvs/upload

Purpose:
Upload a CV file for parsing.

Request:
multipart/form-data with a file field named cv.

Response:
JSON profile draft.
```
