# Model Context Protocol (MCP)

## What it is
MCP is an open standard that lets an AI agent discover and call tools, resources,
and prompts exposed by a server, without custom integration code per service.
It standardizes how an agent lists available capabilities and invokes them.

## Why it matters for agentic readiness
A website or API that exposes an MCP server (or an equivalent machine-readable
tool manifest) gives agents a direct, structured way to act on it — booking,
searching, submitting forms — instead of having to scrape and guess at HTML.

## Key components to detect
- An MCP server manifest (tools, resources, prompts definitions), often reachable
  at a well-known path or referenced in site metadata.
- Tool definitions with a name, description, and JSON-schema input parameters.
- Resource endpoints that expose structured data (not just HTML pages).
- Authentication scheme declared for the MCP server (API key, OAuth, none).

## Common signals in the wild
- A `/.well-known/mcp.json` or similar manifest file.
- References to "mcp", "tools", or "model context protocol" in developer docs,
  robots.txt comments, or llms.txt.
- SDKs or packages named after MCP servers in the site's public repositories.

## Scoring considerations
- Presence of a valid, reachable MCP manifest: strong positive signal.
- Tool descriptions that are vague or missing parameter schemas: partial credit,
  since an agent can find the tool but may misuse it.
- No MCP support at all: agent must fall back to browser-style interaction,
  which is slower and more error-prone.