# Web Security Best Practices

Sources:
OWASP Foundation
Mozilla Web Security Guidelines


## Overview

Web security practices protect websites and APIs against common vulnerabilities and unauthorized access.

Security is an important requirement for reliable interaction between websites and AI agents.


## HTTPS

Web services should use HTTPS to ensure:

- Data encryption
- Authentication of servers
- Protection against interception


## HTTP Security Headers

Security headers improve browser and client protection.

Important headers include:

- Strict-Transport-Security (HSTS)
- Content-Security-Policy (CSP)
- X-Content-Type-Options
- X-Frame-Options
- Referrer-Policy
- Permissions-Policy


## Authentication and Authorization

APIs should clearly define:

- Authentication mechanisms
- Required credentials
- Authorization rules


## Rate Limiting

Services should implement rate limiting to:

- Prevent abuse
- Protect resources
- Ensure availability


## Information Disclosure

Servers should avoid exposing unnecessary information such as:

- Server versions
- Framework details
- Internal implementation information


## Agentic Web Relevance

AI agents interacting with websites require secure and predictable interfaces.

Security improves:

- Trust
- Safe automation
- Protection of user data


## Recommendation Example

If security controls are missing:

Recommendation:
Improve security configuration by enabling HTTPS, adding security headers, and limiting unnecessary information exposure.
