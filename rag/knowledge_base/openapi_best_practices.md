# OpenAPI / Swagger Best Practices for Agent Readiness

## Why OpenAPI matters
An OpenAPI (Swagger) spec gives an agent a machine-readable contract for an API:
endpoints, parameters, request/response schemas, and auth requirements. Agents
can call the API directly instead of parsing HTML or guessing form fields.

## What a good spec provides
- A reachable spec file (commonly `/openapi.json`, `/swagger.json`, or linked
  from API docs pages).
- Clear `operationId` and `summary`/`description` fields per endpoint, since
  agents rely on natural-language descriptions to pick the right call.
- Well-typed request/response schemas (not free-form objects), so an agent can
  construct valid calls without trial and error.
- Documented authentication (API key, Bearer token, OAuth2 flow) directly in
  the spec's `securitySchemes`.
- Realistic examples for request bodies and responses.

## Common gaps that hurt agent usability
- Spec exists but is outdated or doesn't match the live API.
- Missing or generic descriptions ("Endpoint 1") that give an agent no signal
  about what the call does.
- Undocumented rate limits or pagination behavior.
- No versioning strategy, so an agent can't tell which spec matches which
  deployed API version.

## Scoring considerations
- Spec present, valid, and well-documented: high interaction score.
- Spec present but incomplete/stale: moderate score, flag as an issue.
- No spec, only implicit REST conventions: low score, agent must infer
  everything from response shapes.