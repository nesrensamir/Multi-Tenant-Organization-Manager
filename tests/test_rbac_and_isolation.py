import pytest
import pytest_asyncio

@pytest_asyncio.fixture
async def setup_org_and_users(async_client):
    """Helper fixture to set up an admin, a member, and an organization."""
    # 1. Register Admin
    await async_client.post("/auth/register", json={"email": "admin@test.com", "full_name": "Admin", "password": "Pass1234!"})
    admin_token_res = await async_client.post("/auth/login", json={"email": "admin@test.com", "password": "Pass1234!"})
    admin_token = admin_token_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Register Member
    await async_client.post("/auth/register", json={"email": "member@test.com", "full_name": "Member", "password": "Pass1234!"})
    member_token_res = await async_client.post("/auth/login", json={"email": "member@test.com", "password": "Pass1234!"})
    member_token = member_token_res.json()["access_token"]
    member_headers = {"Authorization": f"Bearer {member_token}"}

    # 3. Admin creates Organization
    org_res = await async_client.post("/organizations", json={"org_name": "Test Org"}, headers=admin_headers)
    org_id = org_res.json()["org_id"]

    # 4. Admin invites Member
    await async_client.post(f"/organizations/{org_id}/user", json={"email": "member@test.com", "role": "member"}, headers=admin_headers)

    return {"org_id": org_id, "admin_headers": admin_headers, "member_headers": member_headers}

@pytest.mark.asyncio
async def test_rbac_member_cannot_invite(async_client, setup_org_and_users):
    data = setup_org_and_users  # <-- FIXED: Pytest already awaited this for you!
    
    # Register a random user to try and invite
    await async_client.post("/auth/register", json={"email": "random@test.com", "full_name": "Random", "password": "Pass1234!"})

    # Member tries to invite (Should fail - Admin only)
    response = await async_client.post(
        f"/organizations/{data['org_id']}/user",
        json={"email": "random@test.com", "role": "member"},
        headers=data['member_headers']
    )
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_organization_isolation(async_client, setup_org_and_users):
    data = setup_org_and_users  # <-- FIXED: Pytest already awaited this for you!
    
    # 1. Admin creates an item
    await async_client.post(
        f"/organizations/{data['org_id']}/item",
        json={"org_id": data['org_id'], "item_details": {"name": "Admin Item"}},
        headers=data['admin_headers']
    )

    # 2. Member creates an item
    await async_client.post(
        f"/organizations/{data['org_id']}/item",
        json={"org_id": data['org_id'], "item_details": {"name": "Member Item"}},
        headers=data['member_headers']
    )

    # 3. Member retrieves items (Should only see 1 - their own)
    member_res = await async_client.get(f"/organizations/{data['org_id']}/item", headers=data['member_headers'])
    assert member_res.status_code == 200
    assert len(member_res.json()) == 1
    assert member_res.json()[0]["details"]["name"] == "Member Item"

    # 4. Admin retrieves items (Should see both)
    admin_res = await async_client.get(f"/organizations/{data['org_id']}/item", headers=data['admin_headers'])
    assert admin_res.status_code == 200
    assert len(admin_res.json()) == 2