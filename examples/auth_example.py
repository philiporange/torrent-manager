"""
Example of using the authentication system with the Torrent Manager API.

This demonstrates:
1. Registering a new user
2. Logging in with username/password
3. Accessing protected endpoints
4. Using remember-me functionality
5. Logging out
"""

import asyncio
import httpx


API_BASE_URL = "http://localhost:8000"


async def main():
    async with httpx.AsyncClient(base_url=API_BASE_URL) as client:
        print("=" * 60)
        print("Torrent Manager Authentication Example")
        print("=" * 60)

        # 1. Register a new user
        print("\n1. Registering new user...")
        register_response = await client.post(
            "/auth/register",
            json={
                "username": "demo_user",
                "password": "secure_password_123",
                "email": "demo@example.com"
            }
        )

        if register_response.status_code == 200:
            print("✓ User registered successfully")
            print(f"  User ID: {register_response.json()['user_id']}")
        else:
            print(f"✗ Registration failed: {register_response.json()}")
            return

        # 2. Login with username/password
        print("\n2. Logging in...")
        login_response = await client.post(
            "/auth/login",
            json={
                "username": "demo_user",
                "password": "secure_password_123",
                "remember_me": True  # Enable remember-me functionality
            }
        )

        if login_response.status_code == 200:
            print("✓ Login successful")
            print(f"  Session cookie: {client.cookies.get('session')[:20]}...")
            print(f"  Remember-me cookie: {client.cookies.get('remember_me')[:20]}...")
        else:
            print(f"✗ Login failed: {login_response.json()}")
            return

        # 3. Access protected endpoint (get current user)
        print("\n3. Accessing protected endpoint /auth/me...")
        me_response = await client.get("/auth/me")

        if me_response.status_code == 200:
            user_data = me_response.json()
            print("✓ Successfully accessed protected endpoint")
            print(f"  Username: {user_data['username']}")
            print(f"  Email: {user_data['email']}")
            print(f"  User ID: {user_data['user_id']}")
        else:
            print(f"✗ Failed to access protected endpoint")
            return

        # 4. Access another protected endpoint (list torrents)
        print("\n4. Accessing /torrents endpoint...")
        torrents_response = await client.get("/torrents")

        if torrents_response.status_code == 200:
            print("✓ Successfully accessed torrents endpoint")
            print(f"  Response: {torrents_response.json()}")
        else:
            print(f"✗ Failed to access torrents endpoint")

        # 5. Logout
        print("\n5. Logging out...")
        logout_response = await client.post("/auth/logout")

        if logout_response.status_code == 200:
            print("✓ Logout successful")
            print(f"  Session cookie cleared: {client.cookies.get('session') is None}")
        else:
            print(f"✗ Logout failed")

        # 6. Try to access protected endpoint after logout
        print("\n6. Attempting to access protected endpoint after logout...")
        me_response_after_logout = await client.get("/auth/me")

        if me_response_after_logout.status_code == 401:
            print("✓ Correctly denied access after logout")
        else:
            print("✗ Unexpected: Still have access after logout")

        print("\n" + "=" * 60)
        print("Example completed successfully!")
        print("=" * 60)


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
