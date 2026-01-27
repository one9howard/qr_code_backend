import os
import sys

def check_stripe_key_assignments(root_dir):
    """
    Scans for 'stripe.api_key =' patterns.
    Allowed ONLY in services/stripe_client.py
    """
    failure = False
    allowed_file = os.path.join("services", "stripe_client.py")
    
    for root, dirs, files in os.walk(root_dir):
        if ".git" in dirs:
            dirs.remove(".git")
        if "__pycache__" in dirs:
            dirs.remove("__pycache__")
            
        for name in files:
            if not name.endswith(".py"):
                continue
                
            path = os.path.join(root, name)
            rel_path = os.path.relpath(path, root_dir).replace("\\", "/")
            
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    if "stripe.api_key =" in line or "stripe.api_key=" in line:
                        # Check if allowlisted
                        if rel_path == "services/stripe_client.py" or "check_stripe_key_assignments.py" in rel_path:
                            continue
                            
                        print(f"ERROR: stripe.api_key assignment found in {rel_path}:{i}")
                        print(f"       -> {line.strip()}")
                        failure = True
                        
    if failure:
        print("FAIL: Stripe API key assignments must be centralized in services/stripe_client.py")
        sys.exit(1)
    else:
        print("PASS: Stripe API key assignments are compliant.")
        sys.exit(0)

if __name__ == "__main__":
    check_stripe_key_assignments(os.getcwd())
