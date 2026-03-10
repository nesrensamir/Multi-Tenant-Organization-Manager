import pytest

@pytest.mark.asyncio
async def test_register_user(async_client):
    response = await async_client.post(
        "/auth/register",
        json={"email": "test@example.com", "full_name": "Test User", "password": "StrongPassword123"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data

@pytest.mark.asyncio
async def test_login_user(async_client):
    # Register first
    await async_client.post(
        "/auth/register",
        json={"email": "login@example.com", "full_name": "Login User", "password": "StrongPassword123"}
    )
    
    # Attempt login
    response = await async_client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "StrongPassword123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"