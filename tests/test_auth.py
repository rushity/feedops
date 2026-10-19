"""Tests for Authentication, Registration, and Preferences."""

import pytest
from app.database.db import get_db
from app.services import auth_service


def test_user_registration_success(client, app):
    """Verify consumer can register with age declaration and valid inputs."""
    res = client.post(
        "/auth/register",
        data={
            "email": "consumer@example.com",
            "password": "securepassword123",
            "confirm_password": "securepassword123",
            "display_name": "Test Consumer",
            "role": "consumer",
            "age_confirmed": "1",
            "terms_accepted": "1",
            "consent_personalization": "1",
            "consent_marketing": "1",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Preferences" in html

    with app.app_context():
        db = get_db()
        user = auth_service.get_user_by_email(db, "consumer@example.com")
        assert user is not None
        assert user["role"] == "consumer"
        assert user["is_verified"] == 1

        # Check default consents recorded
        consents = auth_service.get_user_consents(db, user["id"])
        assert consents.get("personalization") is True
        assert consents.get("marketing") is True


def test_registration_age_under_18_blocked(client):
    """Verify user cannot register without confirming 18+ eligibility."""
    res = client.post(
        "/auth/register",
        data={
            "email": "minor@example.com",
            "password": "securepassword123",
            "confirm_password": "securepassword123",
            "role": "consumer",
            "age_confirmed": "0",
            "terms_accepted": "1",
        },
    )
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "18 years of age or older" in html


def test_registration_password_mismatch(client):
    """Verify validation error when passwords do not match."""
    res = client.post(
        "/auth/register",
        data={
            "email": "mismatch@example.com",
            "password": "passwordA",
            "confirm_password": "passwordB",
            "age_confirmed": "1",
            "terms_accepted": "1",
        },
    )
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Passwords do not match" in html


def test_user_login_and_logout(client, app):
    """Verify login and logout flow."""
    with app.app_context():
        db = get_db()
        auth_service.create_user(db, "loginuser@example.com", "pass12345", is_verified=True)

    # Invalid login
    res_bad = client.post("/auth/login", data={"email": "loginuser@example.com", "password": "wrong"})
    assert "Invalid email or password" in res_bad.data.decode("utf-8")

    # Valid login
    res_ok = client.post("/auth/login", data={"email": "loginuser@example.com", "password": "pass12345"}, follow_redirects=True)
    assert res_ok.status_code == 200

    # Logout
    res_logout = client.get("/auth/logout", follow_redirects=True)
    assert res_logout.status_code == 200
    assert "signed out" in res_logout.data.decode("utf-8")


def test_consumer_preference_updates(client, app):
    """Verify consumer can update interests, budget, and brands."""
    with app.app_context():
        db = get_db()
        user = auth_service.create_user(db, "prefuser@example.com", "pass12345", is_verified=True)
        user_id = user["id"]

    # Log in
    client.post("/auth/login", data={"email": "prefuser@example.com", "password": "pass12345"})

    # Post preferences
    res = client.post(
        "/auth/preferences",
        data={
            "interests": ["electronics", "sports"],
            "budget_min": "100",
            "budget_max": "1500",
            "preferred_brands": "Sony, Nike, Apple",
            "currency": "USD",
            "consent_personalization": "1",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        db = get_db()
        prefs = auth_service.get_user_preferences(db, user_id)
        assert "electronics" in prefs["interests"]
        assert "sports" in prefs["interests"]
        assert prefs["budget_min"] == 100.0
        assert prefs["budget_max"] == 1500.0
        assert "Sony" in prefs["preferred_brands"]
        assert "Nike" in prefs["preferred_brands"]
