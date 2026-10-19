"""Authentication and user management service.

Supports Consumer, Merchant, Admin, and Analyst roles.
Uses werkzeug.security for password hashing.
Handles user registration, verification, sessions, and permissions.
"""

from functools import wraps
import json
import secrets
from flask import g, redirect, session, url_for, abort, flash, request
from werkzeug.security import generate_password_hash, check_password_hash


def create_user(db, email: str, password: str, role: str = "consumer", display_name: str = None, phone: str = None, is_verified: bool = False):
    """Create a new user with password hash and default preferences."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("A valid email address is required.")
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    
    allowed_roles = {"consumer", "merchant", "admin", "analyst"}
    if role not in allowed_roles:
        raise ValueError(f"Invalid role. Allowed roles: {', '.join(sorted(allowed_roles))}")

    password_hash = generate_password_hash(password)
    verification_token = secrets.token_hex(16) if not is_verified else None

    try:
        cur = db.execute(
            """INSERT INTO users (email, password_hash, role, display_name, phone, is_verified, verification_token)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (email, password_hash, role, display_name or email.split("@")[0], phone, 1 if is_verified else 0, verification_token),
        )
        user_id = cur.lastrowid

        # Initialize default consumer preferences
        db.execute(
            """INSERT INTO user_preferences (user_id, interests, budget_min, budget_max, preferred_brands, currency)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, json.dumps(["electronics", "home"]), 0, 1000, json.dumps([]), "USD"),
        )

        # Initialize notification preferences
        db.execute(
            """INSERT INTO notification_preferences (user_id, email_alerts, price_drop_alerts, availability_alerts)
               VALUES (?, 1, 1, 1)""",
            (user_id,),
        )

        # Record default mandatory consent
        db.execute(
            """INSERT INTO consent_records (user_id, consent_type, granted, version)
               VALUES (?, 'terms_and_privacy', 1, '1.0')""",
            (user_id,),
        )

        db.commit()
        return get_user_by_id(db, user_id)
    except Exception as exc:
        db.rollback()
        if "UNIQUE" in str(exc).upper():
            raise ValueError("An account with this email already exists.") from exc
        raise


def authenticate_user(db, email: str, password: str):
    """Authenticate a user by email and password. Returns user dict or None."""
    email = (email or "").strip().lower()
    user = get_user_by_email(db, email)
    if not user:
        return None
    if user["status"] != "active":
        return None
    if check_password_hash(user["password_hash"], password):
        return user
    return None


def get_user_by_id(db, user_id: int):
    """Retrieve user record by ID."""
    if not user_id:
        return None
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_email(db, email: str):
    """Retrieve user record by email."""
    if not email:
        return None
    row = db.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    return dict(row) if row else None


def verify_user(db, user_id: int, token: str):
    """Verify user account with verification token."""
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    if user.get("is_verified") == 1:
        return True
    if user.get("verification_token") == token:
        db.execute("UPDATE users SET is_verified = 1, verification_token = NULL WHERE id = ?", (user_id,))
        db.commit()
        return True
    return False


def get_user_preferences(db, user_id: int):
    """Retrieve preferences for a user."""
    row = db.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return {
            "interests": ["electronics", "home"],
            "budget_min": 0,
            "budget_max": 50000,
            "preferred_brands": [],
            "currency": "INR",
        }
    data = dict(row)
    raw_interests = data.get("interests")
    if isinstance(raw_interests, str):
        try:
            data["interests"] = json.loads(raw_interests)
        except Exception:
            data["interests"] = [i.strip() for i in raw_interests.split(",") if i.strip()]
    elif not isinstance(raw_interests, list):
        data["interests"] = []

    raw_brands = data.get("preferred_brands")
    if isinstance(raw_brands, str):
        try:
            data["preferred_brands"] = json.loads(raw_brands)
        except Exception:
            data["preferred_brands"] = [b.strip() for b in raw_brands.split(",") if b.strip()]
    elif not isinstance(raw_brands, list):
        data["preferred_brands"] = []

    if not data.get("currency"):
        data["currency"] = "INR"

    return data


def update_user_preferences(db, user_id: int, interests: list, budget_min: float, budget_max: float, preferred_brands: list = None, currency: str = "INR"):
    """Update consumer preferences with robust numeric parsing and currency support."""
    def _clean_num(v, default):
        if v is None:
            return default
        try:
            s = str(v).replace(",", "").replace("$", "").replace("₹", "").replace("€", "").replace("£", "").strip()
            return float(s)
        except (ValueError, TypeError):
            return default

    b_min = max(0.0, _clean_num(budget_min, 0.0))
    b_max = max(b_min, _clean_num(budget_max, 50000.0))
    interests_json = json.dumps([str(i).strip().lower() for i in interests if str(i).strip()])
    brands_json = json.dumps([str(b).strip() for b in (preferred_brands or []) if str(b).strip()])
    currency_clean = (currency or "INR").strip().upper()[:10]

    db.execute(
        """INSERT INTO user_preferences (user_id, interests, budget_min, budget_max, preferred_brands, currency, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(user_id) DO UPDATE SET
               interests = excluded.interests,
               budget_min = excluded.budget_min,
               budget_max = excluded.budget_max,
               preferred_brands = excluded.preferred_brands,
               currency = excluded.currency,
               updated_at = CURRENT_TIMESTAMP""",
        (user_id, interests_json, b_min, b_max, brands_json, currency_clean),
    )
    db.commit()
    return get_user_preferences(db, user_id)



def record_consent(db, user_id: int, consent_type: str, granted: bool, version: str = "1.0"):
    """Record or update explicit consent state."""
    db.execute(
        """INSERT INTO consent_records (user_id, consent_type, granted, version, timestamp)
           VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (user_id, consent_type, 1 if granted else 0, version),
    )
    db.commit()


def get_user_consents(db, user_id: int):
    """Retrieve the latest consent status for each consent type."""
    rows = db.execute(
        """SELECT consent_type, granted, MAX(timestamp) as latest_ts
           FROM consent_records
           WHERE user_id = ?
           GROUP BY consent_type""",
        (user_id,),
    ).fetchall()
    return {r["consent_type"]: bool(r["granted"]) for r in rows}


# ---------------------------------------------------------------------------
# Authorization and Session Helpers
# ---------------------------------------------------------------------------

def login_user(user: dict):
    """Store user in session."""
    session["user_id"] = user["id"]
    session["user_email"] = user["email"]
    session["user_role"] = user["role"]
    session["user_name"] = user.get("display_name") or user["email"].split("@")[0]


def logout_user():
    """Clear user session."""
    session.pop("user_id", None)
    session.pop("user_email", None)
    session.pop("user_role", None)
    session.pop("user_name", None)


def get_current_user(db):
    """Get active user from session if authenticated."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(db, user_id)


def login_required(f):
    """Decorator requiring a logged-in user."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function


def roles_accepted(*roles):
    """Decorator requiring the logged-in user to have one of the accepted roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please log in to access this area.", "warning")
                return redirect(url_for("auth.login", next=request.path))
            user_role = session.get("user_role")
            if user_role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
