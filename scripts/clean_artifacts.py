import os
import shutil
import sys

def clean_artifacts():
    """
    Clean up ephemeral artifacts (__pycache__, etc.) from the workspace.
    This script MUTATES the workspace.
    """
    root = os.getcwd()
    print(f"Cleaning artifacts in {root}...")
    
    cleaned_count = 0
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip .git, envs
        if '.git' in dirnames: dirnames.remove('.git')
        if '.venv' in dirnames: dirnames.remove('.venv')
        if 'venv' in dirnames: dirnames.remove('venv')
        
        if '__pycache__' in dirnames:
            target = os.path.join(dirpath, '__pycache__')
            try:
                shutil.rmtree(target)
                dirnames.remove('__pycache__')
                cleaned_count += 1
                # print(f"Cleaned: {target}")
            except Exception as e:
                print(f"Failed to clean {target}: {e}")

    print(f"Cleaned {cleaned_count} __pycache__ directories.")
    
    # Optional: Clean .log files?
    # for dirpath, _, filenames in os.walk(root):
    #     for f in filenames:
    #         if f.endswith('.log'):
    #             os.remove(os.path.join(dirpath, f))

if __name__ == "__main__":
    clean_artifacts()
