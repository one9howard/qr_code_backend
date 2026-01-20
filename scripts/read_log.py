
try:
    with open('test_output.log', 'r', encoding='utf-16-le') as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        if any(k in line for k in ["Error", "Traceback", "psycopg2", "AttributeError", "KeyError", "FAILED"]):
            print(f"[{i}] {line.strip()}")
            # Print minimal context
            for j in range(1, 5):
                if i+j < len(lines):
                    print(f"    {lines[i+j].strip()}")
except Exception as e:
    print(f"Failed: {e}")
