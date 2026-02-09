from services.printing.validation import validate_smartsign_payload

def test_v2_validation():
    # Valid
    payload = {
        'agent_name': 'Agent', 
        'agent_phone': '555-1234', 
        'banner_color_id': 'navy',
        'state': 'CA', 
        'show_license_option': 'auto',
        'license_number': '12345',
        'license_label_override': 'DRE #'
    }
    assert validate_smartsign_payload('smart_v2_vertical_banner', payload) == []

    # Invalid State (length)
    errs = validate_smartsign_payload('smart_v2_vertical_banner', {**payload, 'state': 'CAL'})
    assert any("state must be 2-letter" in e for e in errs)

    # Invalid State (chars)
    errs = validate_smartsign_payload('smart_v2_vertical_banner', {**payload, 'state': '12'})
    assert any("state must be 2-letter" in e for e in errs)

    # Invalid Option
    errs = validate_smartsign_payload('smart_v2_vertical_banner', {**payload, 'show_license_option': 'yes'})
    assert any("Invalid show_license_option" in e for e in errs)

    # Invalid License Length
    errs = validate_smartsign_payload('smart_v2_vertical_banner', {**payload, 'license_number': 'x'*65})
    assert any("license_number exceeds" in e for e in errs)
