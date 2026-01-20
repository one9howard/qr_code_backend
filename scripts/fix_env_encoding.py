import os
import sys
# chardet removed to avoid dependency issues

def check_and_fix_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    
    if not os.path.exists(env_path):
        print(f"❌ .env file not found at {env_path}")
        return

    print(f"Analyzing {env_path}...")
    
    # Read raw bytes
    with open(env_path, 'rb') as f:
        raw = f.read()

    print(f"Total size: {len(raw)} bytes")
    
    # Check for BOMs
    encoding = 'utf-8' # Default assumption
    detected_type = "UTF-8/ASCII"
    
    if raw.startswith(b'\xff\xfe'):
        encoding = 'utf-16-le'
        detected_type = "UTF-16 LE BOM"
        print("⚠️  Detailed: Detected UTF-16 LE BOM")
    elif raw.startswith(b'\xfe\xff'):
        encoding = 'utf-16-be'
        detected_type = "UTF-16 BE BOM"
        print("⚠️  Detailed: Detected UTF-16 BE BOM")
    elif raw.startswith(b'\xef\xbb\xbf'):
        encoding = 'utf-8-sig'
        detected_type = "UTF-8 BOM"
        print("ℹ️  Detailed: Detected UTF-8 BOM")
    else:
        # Heuristic for UTF-16 null bytes (if no BOM)
        # If we see null bytes in the first 100 chars, it's likely UTF-16
        if b'\x00' in raw[:100]:
            print("⚠️  Detailed: Null bytes detected (likely UTF-16 without BOM)")
            encoding = 'utf-16' 
            detected_type = "UTF-16 (Nulls)"
        else:
            print("✅  Detailed: No BOM, no nulls. Likely UTF-8 or ASCII.")

    try:
        content = raw.decode(encoding)
        print(f"Successfully decoded as {encoding}")
    except Exception as e:
        print(f"❌ Failed to decode as {encoding}: {e}")
        # Fallback try utf-16 if utf-8 failed
        if encoding == 'utf-8':
            try:
                print("Retrying as utf-16...")
                content = raw.decode('utf-16')
                encoding = 'utf-16'
                print("Success with utf-16 fallback.")
            except:
                return
        else:
            return

    # Check for weird internal chars
    lines = content.splitlines()
    cleaned_lines = []
    issues_found = False
    
    for i, line in enumerate(lines):
        clean = line.strip()
        if not clean:
            cleaned_lines.append("")
            continue
            
        # Check for zero width spaces or other grease
        if '\u200b' in clean:
            print(f"⚠️  Line {i+1}: Zero-width space detected! Removing.")
            clean = clean.replace('\u200b', '')
            issues_found = True
            
        if "STRIPE_PRICE_ANNUAL" in clean:
            print(f"🔎 Line {i+1}: {clean}")
            # Check for non-breaking space
            if '\xa0' in clean:
                print(f"⚠️  Line {i+1}: Non-breaking space detected! Fixing.")
                clean = clean.replace('\xa0', ' ')
                issues_found = True
        
        cleaned_lines.append(clean)
    
    # We always write back if we found encoding issues OR invisible chars
    needs_rewrite = (encoding != 'utf-8') or issues_found
    
    if needs_rewrite:
        print(f"\n🔧 Fixing .env file (Converting {detected_type} -> UTF-8, cleaning chars)...")
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(cleaned_lines))
        print("✅ .env file rewritten as clean UTF-8.")
    else:
        print("✅ .env file structure looks OK (Already UTF-8).")

if __name__ == "__main__":
    check_and_fix_env()
