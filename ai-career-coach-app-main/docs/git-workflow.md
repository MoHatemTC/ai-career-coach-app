# Git Workflow

This project uses a simple branch and pull request workflow.

## Main Branch

`main` should always stay stable.

Do not push feature work directly to `main`.

## Working on a Task

1. Pull the latest `main`.
2. Create a branch.
3. Make focused changes.
4. Commit with the project commit format.
5. Push the branch.
6. Open a pull request.

## Branch Examples

```txt
feature/cv-parser
feature/job-list-page
fix/matcher-score
docs/setup-update
```

## Commit Examples

```txt
feature(cv): add PDF text extraction
fix(jobs): handle missing salary field
docs(api): document job matching endpoint
```

See `CONTRIBUTING.md` for the full policy.
