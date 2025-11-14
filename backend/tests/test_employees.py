"""Integration tests for the employee API."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_login_and_employee_flow(client: AsyncClient) -> None:
    """A user can register, log in, create an employee, and list employees."""

    register_payload = {
        "username": "owner",
        "password": "secret123",
        "account_id": "acme",
        "email": "owner@example.com",
    }
    response = await client.post("/auth/register", json=register_payload)
    assert response.status_code == 201
    user_data = response.json()
    assert user_data["username"] == "owner"

    login_response = await client.post("/auth/login", json=register_payload)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    employee_payload = {
        "code": "E-001",
        "full_name": "Ada Lovelace",
        "email": "ada@example.com",
        "contact_number": "+123456789",
        "position": "Engineer",
        "department": "R&D",
        "basic_salary": 5000.0,
    }
    create_response = await client.post(
        "/employees/", json=employee_payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert create_response.status_code == 201
    employee_data = create_response.json()
    assert employee_data["code"] == "E-001"

    list_response = await client.get("/employees/", headers={"Authorization": f"Bearer {token}"})
    assert list_response.status_code == 200
    employees = list_response.json()
    assert len(employees) == 1
    assert employees[0]["full_name"] == "Ada Lovelace"
