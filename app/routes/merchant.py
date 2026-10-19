"""Merchant and Brand Partner Routes."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from app.database.db import get_db
from app.services import auth_service, partner_service, product_service

merchant_bp = Blueprint("merchant", __name__, url_prefix="/merchant")


def _get_active_partner(db):
    """Retrieve and verify partner record for logged-in user."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return partner_service.get_partner_by_user_id(db, user_id)


@merchant_bp.route("/apply", methods=["GET", "POST"])
@auth_service.login_required
def apply():
    """Merchant / Brand Partner Application."""
    db = get_db()
    user_id = session["user_id"]
    existing = partner_service.get_partner_by_user_id(db, user_id)
    error = None

    if request.method == "POST":
        business_name = request.form.get("business_name", "").strip()
        website = request.form.get("website", "").strip()
        business_email = request.form.get("business_email", "").strip()
        category = request.form.get("category", "").strip()
        partner_type = request.form.get("partner_type", "merchant").strip()

        try:
            partner = partner_service.apply_partner(
                db,
                user_id=user_id,
                business_name=business_name,
                website=website,
                business_email=business_email,
                category=category,
                partner_type=partner_type,
            )
            flash("Your partner application has been submitted and is pending review by platform administrators.", "success")
            return redirect(url_for("merchant.dashboard"))
        except ValueError as exc:
            error = str(exc)

    return render_template("merchant_apply.html", partner=existing, error=error)


@merchant_bp.route("/dashboard")
@auth_service.login_required
def dashboard():
    """Merchant Portal Dashboard."""
    db = get_db()
    partner = _get_active_partner(db)
    if not partner:
        flash("Please complete your merchant application first.", "info")
        return redirect(url_for("merchant.apply"))

    metrics = partner_service.get_merchant_metrics(db, partner["id"])
    recent_imports = partner_service.list_import_jobs(db, partner_id=partner["id"], limit=5)
    recent_products = product_service.search_products(db, partner_id=partner["id"], limit=5, moderation_status=None)

    return render_template(
        "merchant_dashboard.html",
        partner=partner,
        metrics=metrics,
        recent_imports=recent_imports,
        recent_products=recent_products,
    )


@merchant_bp.route("/upload", methods=["GET", "POST"])
@auth_service.login_required
def upload():
    """Upload product catalogue via CSV."""
    db = get_db()
    partner = _get_active_partner(db)
    if not partner:
        flash("Please apply as a partner first.", "warning")
        return redirect(url_for("merchant.apply"))

    if partner["status"] != "approved":
        flash(f"Catalogue uploads are restricted while your application is {partner['status'].title()}. Once approved, you can ingest feeds.", "warning")
        return redirect(url_for("merchant.dashboard"))

    errors = []
    summary = None

    if request.method == "POST":
        csv_file = request.files.get("csv_file")
        csv_text = request.form.get("csv_text", "").strip()

        raw_content = ""
        filename = "pasted_catalogue.csv"

        if csv_file and csv_file.filename:
            filename = csv_file.filename
            try:
                raw_content = csv_file.read().decode("utf-8")
            except UnicodeDecodeError:
                errors.append("Invalid file encoding. Please provide UTF-8 encoded CSV.")
        elif csv_text:
            raw_content = csv_text
        else:
            errors.append("Please upload a CSV file or paste valid CSV content.")

        if raw_content and not errors:
            valid_items, parse_errors = product_service.parse_and_validate_csv(
                raw_content, partner_id=partner["id"], feed_source="csv"
            )
            errors.extend(parse_errors)

            if valid_items:
                result = product_service.import_products_batch(db, partner["id"], valid_items)
                summary = result
                partner_service.record_import_job(
                    db,
                    partner_id=partner["id"],
                    filename=filename,
                    status="completed" if not errors else "partial",
                    items_total=len(valid_items) + len(parse_errors),
                    items_imported=result["imported"],
                    items_skipped=result["skipped"] + len(parse_errors),
                    error_log="\n".join(errors) if errors else None,
                )
                flash(f"Catalogue imported successfully! {result['imported']} products active.", "success")
            else:
                partner_service.record_import_job(
                    db,
                    partner_id=partner["id"],
                    filename=filename,
                    status="failed",
                    items_total=len(parse_errors),
                    items_imported=0,
                    items_skipped=len(parse_errors),
                    error_log="\n".join(errors),
                )

    return render_template("merchant_upload.html", partner=partner, errors=errors, summary=summary)


@merchant_bp.route("/products")
@auth_service.login_required
def products():
    """List and manage products owned by this merchant."""
    db = get_db()
    partner = _get_active_partner(db)
    if not partner:
        flash("Partner account required.", "warning")
        return redirect(url_for("merchant.apply"))

    items = product_service.search_products(db, partner_id=partner["id"], limit=100, moderation_status=None)
    return render_template("merchant_products.html", partner=partner, products=items)


@merchant_bp.route("/imports")
@auth_service.login_required
def imports():
    """Import history and error reports."""
    db = get_db()
    partner = _get_active_partner(db)
    if not partner:
        flash("Partner account required.", "warning")
        return redirect(url_for("merchant.apply"))

    job_history = partner_service.list_import_jobs(db, partner_id=partner["id"], limit=50)
    return render_template("merchant_imports.html", partner=partner, jobs=job_history)


@merchant_bp.route("/campaigns")
@auth_service.login_required
def campaigns():
    """List advertising campaigns owned by this merchant."""
    db = get_db()
    partner = _get_active_partner(db)
    if not partner:
        flash("Partner account required.", "warning")
        return redirect(url_for("merchant.apply"))

    merchant_campaigns = partner_service.list_campaigns(db, partner_id=partner["id"])
    return render_template("merchant_campaigns.html", partner=partner, campaigns=merchant_campaigns)


@merchant_bp.route("/campaigns/new", methods=["GET", "POST"])
@auth_service.login_required
def campaign_new():
    """Create a new sponsored placement campaign."""
    db = get_db()
    partner = _get_active_partner(db)
    if not partner:
        flash("Partner account required.", "warning")
        return redirect(url_for("merchant.apply"))

    if partner.get("status") != "approved":
        flash("Your merchant partner account must be approved by an administrator before creating campaigns.", "warning")
        return redirect(url_for("merchant.campaigns"))

    # Only products belonging to this merchant can be selected (data isolation)
    my_products = product_service.search_products(db, partner_id=partner["id"], limit=200, moderation_status="approved")
    error = None

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        product_id_str = request.form.get("product_id", "").strip()
        start_date = request.form.get("start_date", "").strip()
        end_date = request.form.get("end_date", "").strip()
        daily_budget = request.form.get("daily_budget", "0.0")
        total_budget = request.form.get("total_budget", "0.0")

        try:
            product_id = int(product_id_str)
            partner_service.create_campaign(
                db,
                partner_id=partner["id"],
                product_id=product_id,
                title=title,
                start_date=start_date,
                end_date=end_date,
                daily_budget=daily_budget,
                total_budget=total_budget,
            )
            flash("Campaign submitted successfully. It will become active upon administrator approval.", "success")
            return redirect(url_for("merchant.campaigns"))
        except (ValueError, PermissionError) as exc:
            error = str(exc)

    return render_template("merchant_campaign_new.html", partner=partner, products=my_products, error=error)


@merchant_bp.route("/campaigns/<int:campaign_id>/pause", methods=["POST"])
@auth_service.login_required
def campaign_pause(campaign_id: int):
    """Pause an active campaign."""
    db = get_db()
    partner = _get_active_partner(db)
    if not partner:
        abort(403)

    partner_service.update_campaign_status(db, campaign_id, status="paused", partner_id=partner["id"])
    flash("Campaign paused.", "info")
    return redirect(url_for("merchant.campaigns"))


@merchant_bp.route("/campaigns/<int:campaign_id>/resume", methods=["POST"])
@auth_service.login_required
def campaign_resume(campaign_id: int):
    """Resume a paused campaign."""
    db = get_db()
    partner = _get_active_partner(db)
    if not partner:
        abort(403)

    partner_service.update_campaign_status(db, campaign_id, status="active", partner_id=partner["id"])
    flash("Campaign resumed.", "success")
    return redirect(url_for("merchant.campaigns"))

