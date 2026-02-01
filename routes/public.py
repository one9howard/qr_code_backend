from flask import Blueprint, render_template

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

@public_bp.route("/products")
def products():
    """Display the Products & Pricing page."""
    return render_template("public/products.html")

@public_bp.route("/select-sign")
def select_sign():
    """Display the Sign Selection page (Smart vs Listing)."""
    return render_template("public/select_sign.html")
