
import re

def scan():
    try:
        with open('test_log_3.txt', 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        # Regex for common errors
        patterns = [
            r"AttributeError:.*",
            r"psycopg2\.errors\..*",
            r"KeyError:.*",
            r"AssertionError:.*",
            r"E\s+.*",
            r"FAILED.*"
        ]
        
        found = False
        for p in patterns:
            matches = re.finditer(p, content, re.MULTILINE)
            for m in matches:
                print(f"MATCH: {m.group(0)}")
                # Print context (next 5 lines)
                start = m.end()
                print(content[start:start+500])
                found = True
        
        if not found:
            print("No matches found. Dumping last 2000 chars:")
            print(content[-2000:])
            
    except Exception as e:
        print(f"Error reading log: {e}")

if __name__ == "__main__":
    scan()
