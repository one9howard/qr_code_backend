
def test_import_listing():
    from services.printing.listing_sign import generate_listing_sign_pdf
    assert generate_listing_sign_pdf

def test_import_smart():
    from services.printing.smart_sign import generate_smart_sign_pdf
    assert generate_smart_sign_pdf

def test_import_validation():
    from services.printing.validation import validate_smartsign_payload
    assert validate_smartsign_payload
