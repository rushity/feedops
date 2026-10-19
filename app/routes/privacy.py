"""Privacy, Consent Management, and Notification Routes."""

import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, Response, abort
from app.database.db import get_db
from app.services import auth_service, privacy_service

privacy_bp = Blueprint("privacy", __name__, url_prefix="/privacy")


@privacy_bp.route("/notifications", methods=["GET", "POST"])
@auth_service.login_required
def notifications():
    """Manage user notification preferences and inbox."""
    db = get_db()
    user_id = session["user_id"]
    error = None
    message = None

    if request.method == "POST":
        email_alerts = request.form.get("email_alerts") == "1"
        price_drop_alerts = request.form.get("price_drop_alerts") == "1"
        availability_alerts = request.form.get("availability_alerts") == "1"
        digest_frequency = request.form.get("digest_frequency", "daily")
        quiet_hours_start = request.form.get("quiet_hours_start", "22:00")
        quiet_hours_end = request.form.get("quiet_hours_end", "08:00")
        is_paused = request.form.get("is_paused") == "1"

        try:
            privacy_service.update_notification_preferences(
                db,
                user_id=user_id,
                email_alerts=email_alerts,
                price_drop_alerts=price_drop_alerts,
                availability_alerts=availability_alerts,
                digest_frequency=digest_frequency,
                quiet_hours_start=quiet_hours_start,
                quiet_hours_end=quiet_hours_end,
                is_paused=is_paused,
            )
            message = "Notification settings updated."
        except Exception as exc:
            error = f"Error updating settings: {exc}"

    settings = privacy_service.get_notification_preferences(db, user_id)
    inbox = privacy_service.list_user_notifications(db, user_id)

    return render_template("notifications.html", settings=settings, inbox=inbox, error=error, message=message)


@privacy_bp.route("/consents", methods=["GET", "POST"])
@auth_service.login_required
def consents():
    """Consent governance and revocation."""
    db = get_db()
    user_id = session["user_id"]

    if request.method == "POST":
        consent_type = request.form.get("consent_type")
        granted = request.form.get("granted") == "1"
        if consent_type in ("personalization", "marketing", "location", "voice"):
            auth_service.record_consent(db, user_id, consent_type, granted)
            status_text = "granted" if granted else "revoked"
            flash(f"Consent for {consent_type.title()} has been {status_text}.", "info")
        return redirect(url_for("privacy.consents"))

    user_consents = auth_service.get_user_consents(db, user_id)
    history = db.execute(
        "SELECT * FROM consent_records WHERE user_id = ? ORDER BY id DESC LIMIT 20",
        (user_id,),
    ).fetchall()

    return render_template("consents.html", consents=user_consents, history=[dict(h) for h in history])


@privacy_bp.route("/export")
@auth_service.login_required
def export_data():
    """Download GDPR / DPDP compliant data export JSON file."""
    db = get_db()
    user_id = session["user_id"]
    data = privacy_service.export_user_data(db, user_id)
    if not data:
        abort(404)

    json_str = json.dumps(data, indent=2)
    filename = f"feedops_user_data_export_{user_id}.json"
    return Response(
        json_str,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment;filename={filename}"},
    )


@privacy_bp.route("/delete-account", methods=["GET", "POST"])
@auth_service.login_required
def delete_account():
    """Account erasure request."""
    db = get_db()
    user_id = session["user_id"]
    error = None

    if request.method == "POST":
        confirm_text = request.form.get("confirmation", "").strip()
        if confirm_text != "DELETE MY ACCOUNT":
            error = "Please type 'DELETE MY ACCOUNT' to confirm."
        else:
            auth_service.logout_user()
            privacy_service.execute_account_deletion(db, user_id)
            flash("Your account and all associated personal data have been permanently deleted.", "info")
            return redirect(url_for("consumer.discover"))

    return render_template("delete_account.html", error=error)
