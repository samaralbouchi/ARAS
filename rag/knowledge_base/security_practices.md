# Security Practices Relevant to Agent Interaction

## Transport security
- HTTPS should be enforced site-wide, with HTTP requests redirected, and no
  mixed-content warnings on primary pages.
- Valid, non-expired TLS certificates.

## Authentication methods for APIs
- Prefer standardized, well-documented schemes: API keys in headers, OAuth 2.0
  flows, or signed JWTs, all declared explicitly in API documentation or an
  OpenAPI `securitySchemes` block.
- Avoid undocumented or ad-hoc auth (e.g. secret query parameters with no
  explanation), which forces an agent to guess or fail silently.

## Rate limiting and abuse protection
- Documented rate limits (requests per minute/hour, headers like
  `X-RateLimit-Remaining`) let an agent pace its requests appropriately.
- Undocumented rate limiting that returns opaque errors makes it hard for an
  agent to distinguish a bug from a policy enforcement.

## Security headers
- Presence of standard headers (`Content-Security-Policy`,
  `Strict-Transport-Security`, `X-Content-Type-Options`) is a good general
  hygiene signal, though not agent-specific.

## Scoring considerations
- HTTPS enforced, documented auth, documented rate limits: high security score.
- HTTPS present but auth/rate-limiting undocumented: moderate score, flag as
  an issue affecting reliable agent access.
- HTTP available, no clear auth scheme, undocumented limits: low score, flag
  as a risk for both security and agent reliability.