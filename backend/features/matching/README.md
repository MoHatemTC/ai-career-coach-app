# Matching Feature

## Scoring Design
- **Formula:** We calculate a simple overlap score between the candidate's skills and the job's required skills. The score is the percentage of required skills that are present in the candidate's skill list.
- **Inputs Used:** 
  - Candidate Skills
  - Job Requirements (skills)
- **Ignored for now:** Experience, location, and salary are currently ignored to keep the baseline simple.
- **Match Threshold:** 50%. Any match score >= 50% is considered a potential candidate. This threshold was chosen as a balanced baseline to allow for some flexibility in skill matching while filtering out irrelevant profiles.