"""
Example of using API keys for programmatic authentication.

This demonstrates:
1. Logging in with username/password
2. Creating an API key
3. Using the API key to access protected endpoints
4. Managing API keys (list, revoke)
"""

import asyncio
import httpx


API_BASE_URL = "http://localhost:8000"


async def main():
    print("=" * 60)
    print("Torrent Manager API Key Authentication Example")
    print("=" * 60)

    # Step 1: Login with username/password to create API key
    print("\n1. Logging in with username/password...")
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        # Register a user (or use existing)
        try:
            await client.post("/auth/register", json={
                "username": "api_user",
                "password": "secure_pass_123",
                "email": "api@example.com"
            })
            print("✓ User registered")
        except:
            pass  # User might already exist

        # Login
        login_response = await client.post("/auth/login", json={
            "username": "api_user",
            "password": "secure_pass_123",
            "remember_me": False
        })

        if login_response.status_code != 200:
            print("✗ Login failed")
            return

        print("✓ Logged in successfully")

        # Step 2: Create an API key
        print("\n2. Creating API key...")
        create_key_response = await client.post("/auth/api-keys", json={
            "name": "My Script Key",
            "expires_days": 30  # Optional: expires in 30 days
        })

        if create_key_response.status_code != 200:
            print("✗ Failed to create API key")
            return

        api_key_data = create_key_response.json()
        api_key = api_key_data["api_key"]

        print("✓ API key created successfully")
        print(f"  Name: {api_key_data['name']}")
        print(f"  Key: {api_key[:20]}...")
        print(f"  Expires: {api_key_data['expires_at']}")
        print("\n  ⚠️  Store this API key securely - it won't be shown again!")

    # Step 3: Use the API key to access protected endpoints
    print("\n3. Using API key to access protected endpoints...")
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        # Access /auth/me with API key
        me_response = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {api_key}"}
        )

        if me_response.status_code == 200:
            user_data = me_response.json()
            print("✓ Successfully authenticated with API key")
            print(f"  Username: {user_data['username']}")
            print(f"  Auth method: {user_data['auth_method']}")
        else:
            print("✗ Failed to authenticate with API key")
            return

        # Access /torrents endpoint
        torrents_response = await client.get(
            "/torrents",
            headers={"Authorization": f"Bearer {api_key}"}
        )

        if torrents_response.status_code == 200:
            print("✓ Successfully accessed /torrents endpoint")
            print(f"  Response: {torrents_response.json()}")
        else:
            print("✗ Failed to access /torrents endpoint")

    # Step 4: List API keys
    print("\n4. Listing API keys...")
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        list_response = await client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {api_key}"}
        )

        if list_response.status_code == 200:
            keys = list_response.json()["api_keys"]
            print(f"✓ Found {len(keys)} API key(s)")
            for key in keys:
                print(f"  - {key['name']} ({key['api_key_id']})")
                print(f"    Created: {key['created_at']}")
                if key['last_used_at']:
                    print(f"    Last used: {key['last_used_at']}")
                print(f"    Revoked: {key['revoked']}")

    # Step 5: Revoke the API key
    print("\n5. Revoking API key...")
    key_prefix = api_key[:8]
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        # Use session auth to revoke (login again)
        await client.post("/auth/login", json={
            "username": "api_user",
            "password": "secure_pass_123",
            "remember_me": False
        })

        revoke_response = await client.delete(f"/auth/api-keys/{key_prefix}")

        if revoke_response.status_code == 200:
            print("✓ API key revoked successfully")
        else:
            print("✗ Failed to revoke API key")

        # Try to use the revoked key
        print("\n6. Attempting to use revoked API key...")

    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        test_response = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {api_key}"}
        )

        if test_response.status_code == 401:
            print("✓ Correctly denied access with revoked key")
        else:
            print("✗ Unexpected: Still have access with revoked key")

    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)

    # Summary
    print("\nAPI Key Authentication Summary:")
    print("- API keys provide token-based authentication")
    print("- Pass API key in Authorization header: 'Bearer <key>'")
    print("- API keys can have optional expiration dates")
    print("- API keys can be revoked at any time")
    print("- Perfect for scripts, CLI tools, and automation")


if __name__ == "__main__":
    print("\nMake sure the API server is running:")
    print("  python -m torrent_manager.server\n")

    try:
        asyncio.run(main())
    except httpx.ConnectError:
        print("\n✗ Error: Could not connect to API server.")
        print("  Please start the server first: python -m torrent_manager.server")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
