# Authentication System

This document describes the secure session-based authentication system implemented for the Torrent Manager API.

## Overview

The authentication system uses server-set, HTTP-only secure session cookies with sliding expiration and optional remember-me functionality. This approach provides strong security while maintaining good user experience.

## Features

### Session Management
- **Opaque Session Tokens**: Cryptographically secure random tokens (64 characters)
- **HTTP-Only Cookies**: Prevents XSS attacks by making cookies inaccessible to JavaScript
- **Secure Flag**: Cookies only sent over HTTPS in production
- **SameSite=Lax**: CSRF protection while allowing normal navigation
- **Sliding Expiration**: Session automatically renewed on each user interaction

### Sliding Expiration (ITP-Safe)
- **7-Day Sliding Window**: Sessions renewed only if last activity was within 7 days
- **30-Day Maximum Age**: Sessions expire after 30 days regardless of activity
- **ITP-Safe Design**: Sliding window < 7 days ensures compatibility with Intelligent Tracking Prevention

### Remember-Me Functionality
- **Longer-Lived Tokens**: 90-day expiration for remember-me tokens
- **Automatic Session Renewal**: Creates new session when session expires but remember-me token is valid
- **Secure Storage**: Tokens stored server-side with same security as sessions

## Cookie Format

### Session Cookie
```
Set-Cookie: session=<opaque-token>; Path=/; Secure; HttpOnly; SameSite=Lax; Expires=<date>
```

### Remember-Me Cookie
```
Set-Cookie: remember_me=<opaque-token>; Path=/; Secure; HttpOnly; SameSite=Lax; Expires=<date>
```

## Authentication Methods

The API supports two authentication methods:

### 1. Session-Based Authentication (Browser)
Uses HTTP-only secure cookies with sliding expiration. Best for web browsers and interactive sessions.

### 2. API Key Authentication (Programmatic)
Uses Bearer tokens in the Authorization header. Best for scripts, CLI tools, and automation.

```http
Authorization: Bearer <api_key>
```

## API Endpoints

### Authentication Endpoints

#### Register User
```http
POST /auth/register
Content-Type: application/json

{
  "username": "string",
  "password": "string",
  "email": "string"
}
```

#### Login
```http
POST /auth/login
Content-Type: application/json

{
  "username": "string",
  "password": "string",
  "remember_me": boolean
}
```

Response sets session cookie and optionally remember-me cookie.

#### Logout
```http
POST /auth/logout
```

Requires authentication. Deletes session and revokes remember-me token.

#### Get Current User
```http
GET /auth/me
```

Requires authentication. Returns current user information including auth method used.

### API Key Management Endpoints

#### Create API Key
```http
POST /auth/api-keys
Content-Type: application/json

{
  "name": "string",
  "expires_days": integer (optional)
}
```

Requires authentication (session or API key). Creates a new API key for programmatic access.

Response includes the API key value - store it securely as it won't be shown again.

#### List API Keys
```http
GET /auth/api-keys
```

Requires authentication. Returns all API keys for the current user (key values are masked).

#### Revoke API Key
```http
DELETE /auth/api-keys/{key_prefix}
```

Requires authentication. Revokes an API key by its prefix (first 8 characters).

### Protected Endpoints

All other endpoints require authentication via:
- Session cookie (for browser-based access)
- API key in Authorization header (for programmatic access)

If session is invalid but remember-me token is valid, a new session is automatically created.

## Security Features

### Password Security
- **Bcrypt Hashing**: Passwords hashed using bcrypt with automatic salt generation
- **No Plain-Text Storage**: Passwords never stored in plain text

### Session Security
- **Secure Random Tokens**: Generated using `secrets.token_urlsafe()`
- **Server-Side Validation**: All session data stored server-side
- **IP and User-Agent Tracking**: Sessions track client information
- **Automatic Cleanup**: Expired sessions and tokens automatically removed

### Cookie Security
- **HttpOnly**: Prevents JavaScript access
- **Secure**: HTTPS-only in production (configurable via `COOKIE_SECURE` env var)
- **SameSite=Lax**: CSRF protection while allowing normal navigation
- **Path=/**: Cookies sent to all paths

## Using API Keys

### Creating an API Key

First, authenticate with username/password to create an API key:

```python
import httpx

async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
    # Login
    await client.post("/auth/login", json={
        "username": "user",
        "password": "pass",
        "remember_me": False
    })

    # Create API key
    response = await client.post("/auth/api-keys", json={
        "name": "My Script Key",
        "expires_days": 90  # Optional: key expires in 90 days
    })

    api_key = response.json()["api_key"]
    print(f"API Key: {api_key}")
    # Store this securely - it won't be shown again!
```

### Using an API Key

Once you have an API key, use it in the Authorization header:

```python
import httpx

API_KEY = "your-api-key-here"

async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
    # Access protected endpoints
    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )

    print(response.json())
```

### Using with curl

```bash
curl -H "Authorization: Bearer <api_key>" http://localhost:8000/auth/me
```

### Managing API Keys

```python
# List your API keys
response = await client.get(
    "/auth/api-keys",
    headers={"Authorization": f"Bearer {API_KEY}"}
)

# Revoke an API key (using first 8 characters)
await client.delete(
    "/auth/api-keys/abc12345",
    headers={"Authorization": f"Bearer {API_KEY}"}
)
```

## Database Schema

### Session Table
```python
session_id          VARCHAR(64)  PRIMARY KEY
user_id             VARCHAR
created_at          DATETIME
last_activity       DATETIME
expires_at          DATETIME
ip_address          VARCHAR
user_agent          VARCHAR
```

### RememberMeToken Table
```python
token_id            VARCHAR(64)  PRIMARY KEY
user_id             VARCHAR
created_at          DATETIME
expires_at          DATETIME
ip_address          VARCHAR
user_agent          VARCHAR
revoked             BOOLEAN
```

### ApiKey Table
```python
api_key             VARCHAR(64)  PRIMARY KEY
user_id             VARCHAR
name                VARCHAR
created_at          DATETIME
last_used_at        DATETIME
expires_at          DATETIME (nullable)
revoked             BOOLEAN
```

## Configuration

### Environment Variables

- `COOKIE_SECURE`: Set to "false" to disable Secure flag (for development/testing)
- `SQLITE_DB_PATH`: Path to SQLite database

### Constants (in auth.py)

- `SESSION_SLIDING_WINDOW_DAYS = 7`: Sliding window for session renewal
- `SESSION_MAX_AGE_DAYS = 30`: Maximum session lifetime
- `REMEMBER_ME_MAX_AGE_DAYS = 90`: Remember-me token lifetime

## Running the Server

### Production
```bash
python server.py
```

This starts the server on `http://127.0.0.1:8000` with secure cookies enabled.

### Development
```bash
python server.py --reload --host 0.0.0.0
```

For testing without HTTPS, set:
```bash
export COOKIE_SECURE=false
python server.py --reload
```

### API Documentation
Interactive API documentation available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Testing

Run the authentication test suite:
```bash
# Test session-based authentication
pytest tests/test_auth.py -v

# Test API key authentication
pytest tests/test_api_keys.py -v

# Run all authentication tests
pytest tests/test_auth.py tests/test_api_keys.py -v
```

The tests cover:
- User registration and authentication
- Session creation and validation
- Sliding expiration logic
- Remember-me functionality
- API key creation and validation
- API key authentication
- API key management (list, revoke)
- Protected endpoint access
- Session and token cleanup

## Implementation Files

- `src/torrent_manager/auth.py`: Session, user, and API key management
- `src/torrent_manager/api.py`: FastAPI application and endpoints
- `src/torrent_manager/models.py`: Database models (User, Session, RememberMeToken, ApiKey)
- `tests/test_auth.py`: Session authentication test suite
- `tests/test_api_keys.py`: API key authentication test suite
- `server.py`: Server runner script
- `examples/auth_example.py`: Usage example for session auth

## Security Best Practices

1. **Always use HTTPS in production** to protect cookies in transit
2. **Regularly clean up expired sessions** to prevent database bloat
3. **Monitor failed authentication attempts** for potential attacks
4. **Use strong password requirements** for user registration
5. **Consider rate limiting** on authentication endpoints
6. **Enable CORS** only for trusted domains
7. **Keep dependencies updated** to patch security vulnerabilities

## Future Enhancements

Potential improvements for the authentication system:

- Multi-factor authentication (MFA/2FA)
- OAuth2/OpenID Connect integration
- Session device management (view/revoke active sessions)
- Password reset functionality
- Email verification for new accounts
- Rate limiting on login attempts
- Account lockout after failed attempts
- Audit logging for security events
