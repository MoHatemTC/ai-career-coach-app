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
## POST /skill-gap/analyze

Purpose:
Compare a user's held skills against a target role's required skills
(derived from matched job postings, or an explicit override) and
return a prioritized list of missing skills with reasons.

Request (job-postings mode):
```json
{
  "user_id": "u123",
  "target_role": "Data Analyst",
  "skills": ["Python", "excel"],
  "job_postings_skills": [["Python", "SQL", "Power BI"], ["SQL", "Excel"]]
}
```

Request (explicit override mode):
```json
{
  "user_id": "u123",
  "target_role": "Backend Engineer",
  "skills": ["Python"],
  "required_skills": ["Python", "Docker", "Kubernetes"]
}
```

Response:
```json
{
  "user_id": "u123",
  "target_role": "Data Analyst",
  "required_skills": ["Python", "SQL", "Power BI", "Excel"],
  "held_skills": ["Python", "Excel"],
  "matched_skills": ["Excel", "Python"],
  "gaps": [
    {"skill": "SQL", "category": "language", "priority": 1, "reason": "..."},
    {"skill": "Power BI", "category": "tool", "priority": 2, "reason": "..."}
  ]
}
```

Error cases:
- `400` - neither `job_postings_skills` nor `required_skills` supplied.

