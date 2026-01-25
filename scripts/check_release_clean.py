#!/usr/bin/env python3
import os
import sys

def check_clean(root_dir):
    """
    Traverse directory and fail if __pycache__ or .pyc or .log or _cmd_out.txt found.
    """
    dirty = False
    for root, dirs, files in os.walk(root_dir):
        # Check directories
        if "__pycache__" in dirs:
            print(f"[DIRTY] Found __pycache__ in {root}")
            dirty = True
            
        # Check files
        for f in files:
            if f.endswith(".pyc"):
                print(f"[DIRTY] Found bytecode {f} in {root}")
                dirty = True
            if f.endswith("_cmd_out.txt"):
                print(f"[DIRTY] Found temporary output {f} in {root}")
                dirty = True
            if f.endswith(".log"):
                print(f"[DIRTY] Found log file {f} in {root}")
                dirty = True
                
    return dirty

if __name__ == "__main__":
    print(f"Checking {os.getcwd()} for dirty artifacts...")
    is_dirty = check_clean(".")
    
    if is_dirty:
        print("FAILURE: Repository contains dirty artifacts. Run 'python -m compileall -q .' only in build context or clean before release.")
        sys.exit(1)
        
    print("SUCCESS: Repository is clean.")
    sys.exit(0)
