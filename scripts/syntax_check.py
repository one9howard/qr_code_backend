import ast
import os
import sys

def check_syntax(directory):
    failed = False
    print(f"Checking syntax in {directory} (using ast.parse)...")
    for root, _, files in os.walk(directory):
        if "__pycache__" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        source = f.read()
                    ast.parse(source, filename=path)
                except SyntaxError as e:
                    print(f"Syntax error in {path}: {e}")
                    failed = True
                except Exception as e:
                    print(f"Error checking {path}: {e}")
                    failed = True
    return not failed

if __name__ == "__main__":
    if check_syntax("."):
        print("Syntax check passed.")
        sys.exit(0)
    else:
        print("Syntax check failed.")
        sys.exit(1)
