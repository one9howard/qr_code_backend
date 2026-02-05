#!/usr/bin/env python
"""
Fixture-Driven SmartSign Sample Generator

Generates sample SmartSign PDFs using data from a fixture file.
Does not require database access.

Usage:
    python scripts/generate_smartsign_samples.py
    
    # Use custom fixture file:
    SMARTSIGN_SAMPLES_FIXTURE=/path/to/fixture.json python scripts/generate_smartsign_samples.py
    
Output directory: tmp/smartsign_samples/
"""

import os
import sys
import json

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Default fixture path
DEFAULT_FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'fixtures', 'smartsign_samples.json'
)

# Output directory
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'tmp', 'smartsign_samples'
)


def load_fixture():
    """Load sample data from fixture file."""
    fixture_path = os.environ.get('SMARTSIGN_SAMPLES_FIXTURE', DEFAULT_FIXTURE)
    
    if not os.path.exists(fixture_path):
        print(f"[ERROR] Fixture file not found: {fixture_path}")
        sys.exit(1)
    
    with open(fixture_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data.get('samples', [])


def generate_sample(sample_data, output_dir, index):
    """Generate a single sample PDF from fixture data."""
    from services.pdf_smartsign import generate_smartsign_pdf
    import services.printing.layout_utils as lu
    
    # Register fonts first
    lu.register_fonts()
    
    layout_id = sample_data.get('layout_id', 'smart_v1_minimal')
    size = sample_data.get('size', '18x24')
    agent = sample_data.get('agent', {})
    
    # Validated strict extraction (no defaults)
    try:
        asset = {
            'code': f'SAMPLE{index:03d}',
            'print_size': sample_data['size'],
            'layout_id': sample_data['layout_id'],
            'agent_name': sample_data['agent']['name'],
            'agent_phone': sample_data['agent']['phone'],
            'agent_email': sample_data['agent']['email'],
            'brokerage_name': sample_data['agent']['brokerage'],
            'brand_name': sample_data['agent']['brokerage'], # Legacy compat
            'phone': sample_data['agent']['phone'],          # Legacy compat
            'email': sample_data['agent']['email'],          # Legacy compat
            
            'background_style': sample_data.get('background_style', 'navy'),
            'banner_color_id': sample_data.get('banner_color_id', 'navy'),
            'cta_key': sample_data.get('cta_key', 'scan_for_details'),
            'status_text': sample_data.get('status_text', 'FOR SALE'),
            
            # License fields (V2 strict)
            'state': sample_data.get('state'),
            'license_number': sample_data.get('license_number'),
            'show_license_option': sample_data.get('show_license_option'), 
            'license_label_override': sample_data.get('license_label_override'),
            
            # No images for samples
            'include_logo': False,
            'include_headshot': False,
            'logo_key': None,
            'headshot_key': None,
        }
    except KeyError as e:
        print(f"  [ERROR] Fixture missing required field: {e}")
        return None
    
    # Generate filename
    filename = f"sample_{layout_id}_{size.replace('x', '_')}.pdf"
    output_path = os.path.join(output_dir, filename)
    
    # Generate PDF
    # Note: generate_smartsign_pdf writes to storage.
    # For standalone generation, we patch the storage to write locally.
    from unittest.mock import MagicMock, patch
    from io import BytesIO
    
    captured_pdf = {}
    
    def mock_put_file(data, key, **kwargs):  # Accept content_type etc.
        if hasattr(data, 'seek'):
            data.seek(0)
        if hasattr(data, 'read'):
            captured_pdf['data'] = data.read()
        else:
            captured_pdf['data'] = data
        captured_pdf['key'] = key
        return key
    
    mock_storage = MagicMock()
    mock_storage.put_file = mock_put_file
    mock_storage.exists.return_value = False
    mock_storage.get_file.return_value = BytesIO(b'')
    
    with patch('services.pdf_smartsign.get_storage', return_value=mock_storage):
        try:
            key = generate_smartsign_pdf(asset, order_id=index, user_id=1)
            
            # Write captured PDF to local file
            if 'data' in captured_pdf:
                with open(output_path, 'wb') as f:
                    f.write(captured_pdf['data'])
                return output_path
            else:
                print(f"  [WARN] No PDF data captured for {filename}")
                return None
                
        except Exception as e:
            print(f"  [ERROR] Failed to generate {filename}: {e}")
            import traceback
            traceback.print_exc()
            return None


def main():
    print("=" * 60)
    print("SmartSign Sample Generator (Fixture-Driven)")
    print("=" * 60)
    
    # Load fixtures
    print("\n>>> Loading fixture data...")
    samples = load_fixture()
    print(f"    Found {len(samples)} sample(s) to generate.")
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"    Output directory: {OUTPUT_DIR}")
    
    # Generate samples
    print("\n>>> Generating samples...")
    generated = []
    
    for i, sample in enumerate(samples, start=1):
        layout_id = sample.get('layout_id', 'unknown')
        size = sample.get('size', '?')
        print(f"    [{i}/{len(samples)}] {layout_id} @ {size}...")
        
        output_path = generate_sample(sample, OUTPUT_DIR, i)
        if output_path:
            print(f"        -> {output_path}")
            generated.append(output_path)
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Generated {len(generated)}/{len(samples)} sample PDFs.")
    print("=" * 60)
    
    # Print all generated paths (useful for CI/scripts)
    if generated:
        print("\nGenerated files:")
        for path in generated:
            print(path)
    
    return 0 if len(generated) == len(samples) else 1


if __name__ == "__main__":
    sys.exit(main())
