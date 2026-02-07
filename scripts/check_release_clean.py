import os
import sys

def check_release_clean():
    """Fail if artifacts exist."""
    root = os.getcwd()
    
    # Allowed PDF locations (fixtures only)
    allowed_pdf_dirs = [
        os.path.join(root, "tests", "fixtures"),
        os.path.join(root, "tests", "data")
    ]
    
    errors = []
    
    # Files to ban
    banned_extensions = ['.log', '.sqlite', '.DS_Store']
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip .git, envs
        if '.git' in dirnames: dirnames.remove('.git')
        if '.venv' in dirnames: dirnames.remove('.venv')
        if 'venv' in dirnames: dirnames.remove('venv')
        if '__pycache__' in dirnames:
            errors.append(f"Found __pycache__ in {dirpath}")
            
        # Hard fail on instance/ runtime artifacts (but allow the dir itself if empty/gitkeep?)
        if 'instance' in dirpath.split(os.sep):
            # Checking if instance contains files (except maybe .gitignore)
            for f in filenames:
                if f != '.gitignore':
                    errors.append(f"Found runtime artifact in instance/: {os.path.join(dirpath, f)}")
                    
        # Hard fail on tmp/
        if 'tmp' in dirpath.split(os.sep):
             for f in filenames:
                 if f != '.gitignore':
                     errors.append(f"Found file in tmp/: {os.path.join(dirpath, f)}")

        for f in filenames:
            path = os.path.join(dirpath, f)
            
            # Check PDFs
            if f.endswith('.pdf'):
                is_allowed = False
                for allowed in allowed_pdf_dirs:
                    if path.startswith(allowed):
                        is_allowed = True
                        break
                if not is_allowed:
                    errors.append(f"Found PDF artifact: {path}")
            
            # Check Banned
            for ext in banned_extensions:
                if f.endswith(ext):
                    errors.append(f"Found banned file ({ext}): {path}")
                    
    if errors:
        print("Release Check FAILED:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
        
    print("Release Check PASSED.")
    sys.exit(0)

if __name__ == "__main__":
    check_release_clean()
