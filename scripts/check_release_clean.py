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
    
    # Banned extensions and patterns
    banned_extensions = ['.log', '.sqlite', '.DS_Store', '.pyc', '.pyo', '.pyi', '.dump']
    banned_patterns = ['dump.sql', 'dump.wkr']
    banned_prefixes = ['debug_']
    banned_dir_names = ['__pycache__', 'instance', 'tmp']

    for dirpath, dirnames, filenames in os.walk(root):
        # Exclude common dev/system dirs completely from traversal
        for skip_dir in ['.git', '.venv', 'venv', 'node_modules']:
            if skip_dir in dirnames:
                dirnames.remove(skip_dir)

        # 1. Check for banned directories by name
        rel_path = os.path.relpath(dirpath, root)
        parts = rel_path.split(os.sep)
        
        # If any part of the path is in banned_dir_names, check for actual files
        for part in parts:
            if part in banned_dir_names:
                # Ignore .gitignore files in these directories
                artifacts = [f for f in filenames if f != '.gitignore']
                if artifacts:
                    errors.append(f"Forbidden directory '{part}' contains artifacts: {dirpath}")
                break

        # 2. Check filenames for banned patterns
        for f in filenames:
            path = os.path.join(dirpath, f)
            
            # Check PDFs (only allowed in tests/fixtures or tests/data)
            if f.endswith('.pdf'):
                is_allowed = False
                for allowed in allowed_pdf_dirs:
                    if path.startswith(allowed):
                        is_allowed = True
                        break
                if not is_allowed:
                    errors.append(f"Found PDF artifact: {path}")
            
            # Check Banned Extensions
            for ext in banned_extensions:
                if f.endswith(ext):
                    errors.append(f"Found banned file ({ext}): {path}")
            
            # Check Banned Exact Patterns
            if f in banned_patterns:
                errors.append(f"Found banned file (pattern): {path}")
                
            # Check Banned Prefixes (debug_*)
            for prefix in banned_prefixes:
                if f.startswith(prefix):
                    errors.append(f"Found debug artifact: {path}")
                    
    if errors:
        print("Release Check FAILED:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
        
    print("Release Check PASSED.")
    sys.exit(0)

if __name__ == "__main__":
    check_release_clean()
