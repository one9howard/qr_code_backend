import os
import sys
import re

# Add project root needed for imports if running from scripts/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from services.pdf_smartsign import SPECS
except ImportError:
    # Try alternate path if generic run
    sys.path.append(os.getcwd())
    from services.pdf_smartsign import SPECS

SPECS_MD_PATH = os.path.join(os.path.dirname(__file__), '..', 'SPECS.md')

def parse_specs_md():
    """
    Parses SPECS.md to extract numeric values for verification.
    Focuses on Font sizes to catch drifts.
    Format in MD: "- [Key]: **[size] / [min]**"
    """
    with open(SPECS_MD_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex to find Sections like "### 5.3 24x36"
    # Then find fonts within that section.
    
    extracted = {}
    
    # 1. Split by size headers
    # Regex for headers: "### [number].[number] [Width]x[Height]"
    sections = re.split(r'### \d+\.\d+ (\d+x\d+)', content)
    
    # sections[0] is intro. sections[1] is size key, sections[2] is content, sections[3] is size key...ers
    
    current_layout_context = "unknown"
    
    # Since layout sections are separated by H2 headers "## 5) Modern Minimal..."
    # We should split by H2 first to get layout context.
    
    layout_map = {
        'Modern Minimal': 'smart_v1_minimal',
        'Agent Brand': 'smart_v1_agent_brand',
        'Photo Banner': 'smart_v1_photo_banner'
    }
    
    h2_chunks = re.split(r'## \d+\) ([^\n]+)', content)
    
    for i in range(1, len(h2_chunks), 2):
        header = h2_chunks[i]
        body = h2_chunks[i+1]
        
        layout_id = None
        for k, v in layout_map.items():
            if k in header:
                layout_id = v
                break
        
        if not layout_id:
            continue
            
        # Now parse sizes in this body
        size_chunks = re.split(r'### \d+\.\d+ (\d+x\d+)', body)
        
        for j in range(1, len(size_chunks), 2):
            size_key = size_chunks[j] # e.g. "24x36"
            size_body = size_chunks[j+1]
            
            # Parse Fonts
            # Line format: "- [Name]: **[Start] / [Min]**"
            font_matches = re.findall(r'- ([^:]+): \*\*(\d+) / (\d+)\*\*', size_body)
            
            for fname, start, min_sz in font_matches:
                # Map MD name to dict key
                key_map = {
                    'Agent name': 'name',
                    'Name': 'name',
                    'Phone': 'phone',
                    'Email': 'email',
                    'Brokerage': 'brokerage',
                    'CTA': 'cta',
                    'CTA line1': 'cta1',
                    'CTA line2': 'cta2',
                    'CTA1': 'cta1',
                    'CTA2': 'cta2',
                    'URL': 'url',
                    '“Scan Me” label': 'scan_label',
                    '“Scan Me”': 'scan_label'
                }
                
                clean_name = fname.split('(')[0].strip() # Remove "(max 2 lines)"
                # Handle fancy quotes
                clean_name = clean_name.replace('“', '').replace('”', '').replace('"', '')
                
                code_key = key_map.get(clean_name, clean_name.lower())
                
                # Check mapping
                if code_key not in ['name', 'phone', 'email', 'brokerage', 'cta', 'cta1', 'cta2', 'url', 'scan_label']:
                     # Might be a key we missed or don't care about for this strict pass
                     continue
                     
                # Store
                if size_key not in extracted: extracted[size_key] = {}
                if layout_id not in extracted[size_key]: extracted[size_key][layout_id] = {}
                
                extracted[size_key][layout_id][code_key] = (int(start), int(min_sz))

    return extracted

def text_check():
    md_specs = parse_specs_md()
    errors = []
    
    for size, layouts in md_specs.items():
        if size not in SPECS:
            continue
            
        for layout_id, fonts in layouts.items():
            if layout_id not in SPECS[size]:
                continue
                
            code_fonts = SPECS[size][layout_id].get('fonts', {})
            
            for font_key, (md_start, md_min) in fonts.items():
                if font_key not in code_fonts:
                    # Some keys might be optional or missing in code (e.g. scan_label in minimal)
                    continue
                    
                code_val = code_fonts[font_key]
                # code_val is (start, min)
                
                if code_val != (md_start, md_min):
                    errors.append(f"Mismatch {size} {layout_id} [{font_key}]: MD says {md_start}/{md_min}, Code has {code_val}")

    if errors:
        print("SPECS DRIFT DETECTED:")
        for e in errors:
            print(f"  [FAIL] {e}")
        sys.exit(1)
    else:
        print("SPECS SYNC CHECK PASSED")
        sys.exit(0)

if __name__ == "__main__":
    text_check()
