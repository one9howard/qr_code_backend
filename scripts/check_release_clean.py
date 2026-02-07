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
    
    # Files to ban (Log files, db artifacts, system junk)
    banned_extensions = ['.log', '.sqlite', '.DS_Store']
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip .git, envs
        if '.git' in dirnames: dirnames.remove('.git')
        if '.venv' in dirnames: dirnames.remove('.venv')
        if 'venv' in dirnames: dirnames.remove('venv')

        # Only evaluate banned directories relative to this repo root (NOT system temp paths)
        rel_parts = os.path.relpath(dirpath, root).split(os.sep)
        
        # Hard fail on instance/ runtime artifacts (repo-relative only)
        if 'instance' in rel_parts:
            for f in filenames:
                if f != '.gitignore':
                    errors.append(f"Found runtime artifact in instance/: {os.path.join(dirpath, f)}")
                    
        # Hard fail on tmp/ (repo-relative only)
        if 'tmp' in rel_parts:
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
