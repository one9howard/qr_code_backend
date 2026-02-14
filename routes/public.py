from flask import Blueprint, render_template, redirect, url_for

public_bp = Blueprint('public', __name__)

@public_bp.route("/")
def landing():
    return render_template("landing.html")

@public_bp.route("/home")
def home():
    return render_template("home.html")

@public_bp.route("/about")
def about():
    return render_template("about.html")

@public_bp.route("/privacy")
def privacy():
    """Display the Privacy Policy page."""
    return render_template("privacy.html")

@public_bp.route("/terms")
def terms():
    """Display the Terms of Service page."""
    return render_template("terms.html")

@public_bp.route("/pricing")
def pricing():
    """Redirect to the landing page pricing section."""
    return redirect("/#plans")


@public_bp.route("/order")
def legacy_order():
    """Legacy order route kept for backward compatibility."""
    return redirect(url_for("public.select_sign"), code=301)



@public_bp.route("/select-sign")
def select_sign():
    """Display the Sign Selection page (Smart vs Listing)."""
    return render_template("public/select_sign.html")
