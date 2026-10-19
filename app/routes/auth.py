"""Authentication and Consumer Onboarding Routes."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from app.database.db import get_db
from app.services import auth_service

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user account with age verification and role selection."""
    if session.get("user_id"):
        return redirect(url_for("consumer.discover"))

    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        display_name = request.form.get("display_name", "").strip()
        phone = request.form.get("phone", "").strip()
        role = request.form.get("role", "consumer").strip()
        age_confirmed = request.form.get("age_confirmed") == "1"
        terms_accepted = request.form.get("terms_accepted") == "1"

        if not age_confirmed:
            error = "You must confirm you are 18 years of age or older to register."
        elif not terms_accepted:
            error = "You must accept the Terms of Service and Privacy Policy."
        elif password != confirm_password:
            error = "Passwords do not match."
        else:
            db = get_db()
            try:
                user = auth_service.create_user(
                    db,
                    email=email,
                    password=password,
                    role=role if role in ("consumer", "merchant") else "consumer",
                    display_name=display_name,
                    phone=phone,
                    is_verified=True,  # Instant local verification for seamless dev experience
                )
                auth_service.login_user(user)

                # Record explicit consents
                auth_service.record_consent(db, user["id"], "personalization", request.form.get("consent_personalization") == "1")
                auth_service.record_consent(db, user["id"], "marketing", request.form.get("consent_marketing") == "1")

                flash("Welcome to FeedOps Discovery! Configure your preferences to tailor your feed.", "success")
                if user["role"] == "merchant":
                    return redirect(url_for("merchant.apply"))
                return redirect(url_for("auth.preferences"))
            except ValueError as exc:
                error = str(exc)

    return render_template("register.html", error=error)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Log in existing user."""
    if session.get("user_id"):
        return redirect(url_for("consumer.discover"))

    error = None
    next_url = request.args.get("next") or ""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        next_url = request.form.get("next", "")

        db = get_db()
        user = auth_service.authenticate_user(db, email, password)
        if user:
            auth_service.login_user(user)
            flash(f"Welcome back, {user.get('display_name') or user['email']}!", "success")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            if user["role"] == "merchant":
                return redirect(url_for("merchant.dashboard"))
            elif user["role"] == "admin":
                return redirect(url_for("admin.index"))
            return redirect(url_for("consumer.discover"))
        else:
            error = "Invalid email or password."

    return render_template("login.html", error=error, next=next_url)


@auth_bp.route("/logout")
def logout():
    """Log out active user."""
    auth_service.logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("consumer.discover"))


@auth_bp.route("/preferences", methods=["GET", "POST"])
@auth_service.login_required
def preferences():
    """Consumer interests, budget, and brand preferences management."""
    db = get_db()
    user_id = session["user_id"]
    error = None
    message = None

    available_interests = [
        ("electronics", "Electronics & Tech"),
        ("fashion", "Fashion & Apparel"),
        ("home", "Home & Kitchen"),
        ("groceries", "Groceries & Essentials"),
        ("sports", "Sports & Fitness"),
        ("travel", "Travel & Luggage"),
        ("learning", "Books & Learning"),
        ("automotive", "Automotive"),
    ]

    if request.method == "POST":
        selected_interests = request.form.getlist("interests")
        budget_min_raw = request.form.get("budget_min", 0)
        budget_max_raw = request.form.get("budget_max", 50000)
        preferred_brands_raw = request.form.get("preferred_brands", "")
        currency = request.form.get("currency", "INR").strip().upper()

        brands = [b.strip() for b in preferred_brands_raw.split(",") if b.strip()]

        try:
            auth_service.update_user_preferences(
                db,
                user_id=user_id,
                interests=selected_interests,
                budget_min=budget_min_raw,
                budget_max=budget_max_raw,
                preferred_brands=brands,
                currency=currency,
            )
            # Update optional consents
            auth_service.record_consent(db, user_id, "personalization", request.form.get("consent_personalization") == "1")
            auth_service.record_consent(db, user_id, "marketing", request.form.get("consent_marketing") == "1")

            flash("Your preferences and consent choices have been saved!", "success")
            return redirect(url_for("auth.preferences"))
        except Exception as exc:
            error = f"Error saving preferences: {exc}"

    current_prefs = auth_service.get_user_preferences(db, user_id)
    current_consents = auth_service.get_user_consents(db, user_id)

    return render_template(
        "preferences.html",
        prefs=current_prefs,
        consents=current_consents,
        available_interests=available_interests,
        error=error,
        message=message,
    )

