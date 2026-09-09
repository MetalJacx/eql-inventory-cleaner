# Production Release Checklist

## Before first public release

- Confirm game policy/tooling boundaries and publish a read-only usage disclaimer.
- Verify all API endpoints return expected HTTP status codes for success and failure cases.
- Set `API_ALLOWED_ORIGINS` to exact frontend origin(s), no wildcard.
- Confirm upload size limits and user-friendly error messages for oversized files.
- Enable HTTPS on both frontend and API deployments.
- Validate no inventory data is persisted in logs, database, or object storage.

## Quality gates

- Run unit tests in CI on every push and pull request.
- Add API contract tests for `/analyze-file` and `/analyze-text` payload shape.
- Compare API analysis output against known desktop baselines for parity.
- Perform cross-browser smoke tests (Chromium, Firefox, mobile).

## Security and operational checks

- Add security headers on frontend hosting config.
- Pin Python/runtime versions on deploy target.
- Set uptime checks for API health endpoint.
- Add minimal request logging and error correlation IDs.

## Deployment steps

- Deploy API service and verify [health check](../web_api/app.py#L43).
- Deploy frontend and confirm API base URL is set correctly.
- Run end-to-end upload test with a real `/outputfile inventory` export.
- Confirm CORS allows only expected frontend origin.

## Post-release

- Track errors for first 48 hours.
- Collect user feedback for quest-selector workflow.
- Plan and prioritize follow-up fixes before wider rollout.
