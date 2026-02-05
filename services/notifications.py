import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import IS_PRODUCTION

logger = logging.getLogger(__name__)

# SMTP timeout in seconds
SMTP_TIMEOUT = 10

def get_ipv4_address(hostname, port):
    """Resolve hostname to IPv4 address to avoid IPv6 routing issues in containers."""
    try:
        import socket
        # AF_INET forces IPv4
        addr_info = socket.getaddrinfo(hostname, port, family=socket.AF_INET)
        # Returns list of (family, type, proto, canonname, sockaddr)
        # sockaddr is (ip, port)
        if addr_info:
            ip = addr_info[0][4][0]
            logger.info(f"[Notifications] Resolved {hostname} to IPv4: {ip}")
            return ip
    except Exception as e:
        logger.warning(f"[Notifications] Failed to resolve IPv4 for {hostname}: {e}")
    return hostname


def send_lead_notification_email(agent_email, lead_payload):
    """
    Send lead notification to agent via SMTP synchronously.
    
    Returns:
        tuple: (success: bool, error_message: str | None, outcome_status: str)
               outcome_status in {'sent', 'failed', 'skipped'}
    
    lead_payload: dict with keys:
    - buyer_name
    - buyer_email
    - buyer_phone
    - property_address
    - message
    - preferred_contact
    - best_time
    """
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS", "").replace(" ", "")
    sender_email = os.environ.get("NOTIFY_EMAIL_FROM", "noreply@insitesigns.com")
    use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

    subject = f"New Lead: {lead_payload.get('property_address', 'Unknown Property')}"
    
    body = f"""
    You have a new lead!
    
    Property: {lead_payload.get('property_address')}
    
    Buyer: {lead_payload.get('buyer_name')}
    Email: {lead_payload.get('buyer_email')}
    Phone: {lead_payload.get('buyer_phone', 'N/A')}
    
    Contact Preference: {lead_payload.get('preferred_contact', 'Any')}
    Best Time: {lead_payload.get('best_time', 'N/A')}
    
    Message:
    {lead_payload.get('message', 'No message')}
    
    --
    InSite Signs
    """

    if not smtp_host or not smtp_user:
        # No SMTP configured - skip sending
        logger.warning(f"[Notifications] SMTP not configured. Skipping email to agent.")
        return (False, "SMTP not configured", "skipped")

    logger.info(f"[Notifications] Config: Host={smtp_host}, Port={smtp_port}, User={smtp_user}, TLS={use_tls}")
    
    # Force IPv4 resolution - DISABLED (causes SSL Host verify fail)
    effective_host = smtp_host

    try:
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = agent_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        if smtp_port == 465:
            logger.info(f"[Notifications] Attempting SMTP_SSL connection to {effective_host}:{smtp_port}...")
            import ssl
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(effective_host, smtp_port, context=context, timeout=SMTP_TIMEOUT) as server:
                logger.info("[Notifications] Connected. Logging in...")
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            logger.info(f"[Notifications] Attempting SMTP (STARTTLS) connection to {effective_host}:{smtp_port}...")
            with smtplib.SMTP(effective_host, smtp_port, timeout=SMTP_TIMEOUT) as server:
                if use_tls:
                    server.starttls()
                logger.info("[Notifications] Connected. Logging in...")
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        
        logger.info(f"[Notifications] Lead notification sent successfully.")
        return (True, None, "sent")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[Notifications] Failed to send email: {error_msg} (Type: {type(e).__name__})")
        return (False, error_msg, "failed")


def send_verification_email(to_email, code):
    """
    Send verification code email.
    """
    # Debug Helper: Log code only in non-production
    if not IS_PRODUCTION:
        logger.warning(f"[Notifications] DEBUG MODE: Verification Code for {to_email} is: {code}")

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS", "").replace(" ", "")
    sender_email = os.environ.get("NOTIFY_EMAIL_FROM", "noreply@insitesigns.com")
    use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

    subject = "Verify your email - InSite Signs"
    
    body = f"""
    Welcome to InSite Signs!
    
    Your verification code is: {code}
    
    This code will expire in 15 minutes.
    
    --
    InSite Signs
    """

    logger.warning(f"[Notifications] Config: Host={smtp_host}, Port={smtp_port}, User={smtp_user}, TLS={use_tls}")

    # Force IPv4 resolution - DISABLED (causes SSL Host verify fail)
    effective_host = smtp_host

    try:
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        if smtp_port == 465:
            logger.info(f"[Notifications] Attempting SMTP_SSL connection to {effective_host}:{smtp_port}...")
            import ssl
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(effective_host, smtp_port, context=context, timeout=SMTP_TIMEOUT) as server:
                logger.info("[Notifications] Connected. Logging in...")
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            logger.info(f"[Notifications] Attempting SMTP (STARTTLS) connection to {effective_host}:{smtp_port}...")
            with smtplib.SMTP(effective_host, smtp_port, timeout=SMTP_TIMEOUT) as server:
                if use_tls:
                    server.starttls()
                logger.info("[Notifications] Connected. Logging in...")
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        
        logger.info(f"[Notifications] Verification email sent to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"[Notifications] Failed to send verification email: {e} (Type: {type(e).__name__})")
        return False
