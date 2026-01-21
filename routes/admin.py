from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from database import get_db
from services.fulfillment import fulfill_order
from constants import (
    ORDER_STATUS_PAID, 
    ORDER_STATUS_SUBMITTED_TO_PRINTER,
    ORDER_STATUS_PRINT_FAILED,
    ORDER_STATUS_FULFILLED
)

admin_bp = Blueprint('admin', __name__)

@admin_bp.before_request
@login_required
def require_admin():
    if not current_user.is_admin:
        abort(403)

@admin_bp.route("/admin/orders")
def order_list():
    db = get_db()
    # List all orders including guest orders, latest first
    # Use LEFT JOIN to include orders without user_id (guest checkout)
    orders = db.execute('''
        SELECT 
            o.*,
            COALESCE(u.email, o.guest_email) AS customer_email,
            CASE WHEN o.user_id IS NULL THEN 1 ELSE 0 END AS is_guest
        FROM orders o 
        LEFT JOIN users u ON o.user_id = u.id 
        ORDER BY o.created_at DESC
    ''').fetchall()
    return render_template("admin_orders.html", orders=orders)

@admin_bp.route("/admin/orders/<int:order_id>/retry", methods=["POST"])
def retry_fulfillment(order_id):
    db = get_db()
    order = db.execute("SELECT status, order_type FROM orders WHERE id = %s", (order_id,)).fetchone()
    
    if not order:
        flash(f"Order {order_id} not found.", "error")
        return redirect(url_for('admin.order_list'))
    
    current_status = order['status']
    # Ensure dict access for safety
    order_type = dict(order).get('order_type', 'sign') # Default to sign for legacy compatibility
    
    # LAYERED SAFETY: Only allow retries for sign orders
    if order_type != 'sign':
         flash(f"Refused: Order {order_id} is of type '{order_type}'. Only 'sign' orders can be fulfilled.", "error")
         return redirect(url_for('admin.order_list'))

    # Allow retry for 'paid' or 'print_failed' orders
    if current_status == ORDER_STATUS_PRINT_FAILED:
        # Reset to paid so fulfillment will process it
        db.execute(
            "UPDATE orders SET status = %s, fulfillment_error = NULL WHERE id = %s",
            (ORDER_STATUS_PAID, order_id)
        )
        db.commit()
        flash(f"Order {order_id} status reset to 'paid'. Retrying fulfillment...", "info")
    elif current_status != ORDER_STATUS_PAID:
        flash(f"Refused: Order {order_id} is '{current_status}', not 'paid' or 'print_failed'.", "error")
        return redirect(url_for('admin.order_list'))
    
    if fulfill_order(order_id):
        flash(f"Order {order_id} fulfillment retried successfully.", "success")
    else:
        # Check why it failed
        updated_order = db.execute("SELECT status, fulfillment_error FROM orders WHERE id = %s", (order_id,)).fetchone()
        error_msg = updated_order['fulfillment_error'] if updated_order else 'Unknown error'
        flash(f"Retry failed for Order {order_id}: {error_msg}", "error")
            
    return redirect(url_for('admin.order_list'))


@admin_bp.route("/admin/metrics")
def metrics():
    """Admin metrics page showing last 7 days of event counts."""
    db = get_db()
    
    # Get event counts for last 7 days
    metrics_data = db.execute("""
        SELECT 
            event_name,
            COUNT(*) as count
        FROM events
        WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY event_name
        ORDER BY count DESC
    """).fetchall()
    
    # Convert to dict for easy template access
    counts = {row['event_name']: row['count'] for row in metrics_data}
    
    # Get daily breakdown for key events
    daily_breakdown = db.execute("""
        SELECT 
            DATE(created_at) as date,
            event_name,
            COUNT(*) as count
        FROM events
        WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY DATE(created_at), event_name
        ORDER BY DATE(created_at) DESC, event_name
    """).fetchall()
    
    return render_template("admin_metrics.html", 
                         counts=counts, 
                         daily_breakdown=daily_breakdown)
