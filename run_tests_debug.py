
import pytest
import sys
from io import StringIO

if __name__ == "__main__":
    combined_output = StringIO()
    saved_stdout = sys.stdout
    saved_stderr = sys.stderr
    sys.stdout = combined_output
    sys.stderr = combined_output
    
    try:
        ret = pytest.main(["-v", "-s", 
            "tests/test_qr_code_uniqueness.py", 
            "tests/test_dashboard_smartsigns_phase1.py", 
            "tests/test_smart_sign_activation.py"
        ])
    except Exception as e:
        print(f"Exception: {e}")
        ret = -1
    finally:
        sys.stdout = saved_stdout
        sys.stderr = saved_stderr
    
    print(f"Exit code: {ret}")
    with open('verification_output.txt', 'w', encoding='utf-8') as f:
        f.write(combined_output.getvalue())
    print("Output written to verification_output.txt")
