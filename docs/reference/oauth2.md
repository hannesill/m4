# OAuth2 Authentication

Enterprise-grade authentication for M4 using OAuth2 with JWT tokens.

## Quick Setup

```bash
# Enable OAuth2 when configuring
m4 config claude --enable-oauth2 \
  --oauth2-issuer https://your-auth-provider.com \
  --oauth2-audience m4-api
```

## MCP Configuration with OAuth2

For manual MCP client configuration with OAuth2 enabled:

```json
{
  "mcpServers": {
    "m4": {
      "command": "uvx",
      "args": ["m4-infra"],
      "env": {
        "M4_OAUTH2_ENABLED": "true",
        "M4_OAUTH2_ISSUER_URL": "https://your-auth-provider.com",
        "M4_OAUTH2_AUDIENCE": "m4-api",
        "M4_OAUTH2_TOKEN": "your-jwt-token"
      }
    }
  }
}
```

> **Note:** The active backend is configured via `m4 backend duckdb` (or `bigquery`), not through MCP env vars.

## Environment Variables

### Required (when OAuth2 enabled)

```bash
M4_OAUTH2_ENABLED=true
M4_OAUTH2_ISSUER_URL=https://your-auth-provider.com
M4_OAUTH2_AUDIENCE=m4-api
```

### Optional

```bash
# Scopes
M4_OAUTH2_REQUIRED_SCOPES=read:mimic-data    # Default: read:mimic-data

# JWKS (auto-discovered from issuer if not set)
M4_OAUTH2_JWKS_URL=https://your-auth-provider.com/.well-known/jwks.json
M4_OAUTH2_JWKS_CACHE_TTL=3600                # Default: 3600 (1 hour)

# Client credentials (if needed by your provider)
M4_OAUTH2_CLIENT_ID=your-client-id
M4_OAUTH2_CLIENT_SECRET=your-client-secret

# Validation toggles
M4_OAUTH2_VALIDATE_EXP=true                  # Default: true
M4_OAUTH2_VALIDATE_AUD=true                  # Default: true
M4_OAUTH2_VALIDATE_ISS=true                  # Default: true

# Rate limiting
M4_OAUTH2_RATE_LIMIT_ENABLED=true            # Default: true
M4_OAUTH2_RATE_LIMIT_REQUESTS=100            # Default: 100 requests per window
M4_OAUTH2_RATE_LIMIT_WINDOW=3600             # Default: 3600 seconds (1 hour)

# Token (set at runtime)
M4_OAUTH2_TOKEN=your-jwt-token               # Bearer prefix optional
```

## Token Requirements

Your JWT must include:

**Header:**
- `alg`: RS256 or ES256
- `kid`: Key ID matching a key in the JWKS

**Claims:**
```json
{
  "iss": "https://your-auth-provider.com",
  "aud": "m4-api",
  "scope": "read:mimic-data",
  "exp": 1234567890,
  "sub": "user-id"
}
```

## Rate Limiting

Rate limiting is per-user (based on the `sub` claim):

- **Default limit:** 100 requests per hour per user
- **Memory management:** LRU eviction when cache exceeds 10,000 users
- **Cleanup:** Expired entries are periodically removed

Disable rate limiting:
```bash
M4_OAUTH2_RATE_LIMIT_ENABLED=false
```

## Provider Examples

### Auth0

```bash
M4_OAUTH2_ISSUER_URL=https://your-domain.auth0.com/
M4_OAUTH2_AUDIENCE=https://api.your-domain.com
M4_OAUTH2_REQUIRED_SCOPES=read:mimic-data
```

### Okta

```bash
M4_OAUTH2_ISSUER_URL=https://your-domain.okta.com/oauth2/default
M4_OAUTH2_AUDIENCE=api://m4
```

### Any OIDC Provider

Any OAuth2 provider supporting:
- JWKS endpoint (`.well-known/jwks.json`)
- JWT tokens with RS256 or ES256 signing
- Standard claims (`iss`, `aud`, `exp`, `sub`)

## Troubleshooting

### Error: "Missing OAuth2 access token"

Set the token environment variable:
```bash
export M4_OAUTH2_TOKEN="eyJhbGciOiJSUzI1NiIs..."
```

### Error: "Invalid token signature"

- Verify token is signed by the configured issuer
- Check JWKS URL is accessible
- Ensure token's `kid` matches a key in JWKS

### Error: "Missing required scopes"

Request a new token with all required scopes. Check if your provider uses:
- Space-separated scopes in `scope` claim
- Array in `scp` claim (both are supported)

### Error: "Rate limit exceeded"

- Wait for the rate limit window to reset (default: 1 hour)
- Or increase `M4_OAUTH2_RATE_LIMIT_REQUESTS`
- Or disable rate limiting for development

### Error: "Token has expired"

Request a fresh token from your OAuth2 provider.

## Security Best Practices

1. **Use short-lived tokens** (< 1 hour)
2. **Never commit tokens** to version control
3. **Use environment variables** or secure secret storage
4. **Start with conservative rate limits** and adjust based on usage
5. **Monitor authentication failures** in logs

## Disabling OAuth2

For development or local use, OAuth2 is disabled by default:

```bash
M4_OAUTH2_ENABLED=false  # or simply don't set it
```

When disabled, all MCP tools are accessible without authentication.
