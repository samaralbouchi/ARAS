# Robots Exclusion Protocol (robots.txt)

Source:
RFC 9309 - Robots Exclusion Protocol


## Overview

The robots.txt file defines rules that specify which parts of a website automated crawlers are allowed or disallowed to access.

It is located at the root of a website:

https://example.com/robots.txt


## Main Directives

Common directives include:

- User-agent
- Allow
- Disallow
- Sitemap


## User-agent

The User-agent directive specifies which crawler or automated agent the rule applies to.

Example:

User-agent: *


## Disallow

The Disallow directive prevents crawlers from accessing specific paths.

Example:

Disallow: /private/


## Sitemap

The Sitemap directive provides the location of a website sitemap.

Example:

Sitemap: https://example.com/sitemap.xml


## Agentic Web Relevance

For AI agents, robots.txt provides information about:

- Crawling permissions
- Website structure hints
- Available sitemap locations


## Limitations

robots.txt is not a security mechanism.

It only provides crawling instructions and should not be used to protect sensitive information.


## Assessment Criteria

A website should provide:

- A valid robots.txt file
- Clear crawling rules
- Sitemap references when available


## Recommendation Example

If robots.txt is missing:

Recommendation:
Add a robots.txt file to provide clear crawling instructions and improve discoverability for automated agents.
