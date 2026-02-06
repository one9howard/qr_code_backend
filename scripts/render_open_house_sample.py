
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from utils.listing_designs import _draw_open_house_gold, LayoutSpec

def generate_sample():
    filename = "open_house_sample.pdf"
    
    # 24x18 Landscape spec (standard yard sign)
    layout = LayoutSpec(24, 18)
    
    c = canvas.Canvas(filename, pagesize=(24*inch, 18*inch))
    
    # Dummy Data
    _draw_open_house_gold(
        c, layout,
        address="123 Luxury Lane",
        beds="4", baths="3", sqft="2500", price="$1,200,000",
        agent_name="Sarah Jenkins",
        brokerage="Prestige Realty",
        agent_email="sarah@prestigerealty.com",
        agent_phone="555-0199",
        qr_key=None, # Will generate fallback rect or example
        agent_photo_key=None,
        sign_color="#D4AF37",
        qr_value="https://insitesigns.com/openhouse"
    )
    
    c.showPage()
    c.save()
    print(f"Generated {filename}")

if __name__ == "__main__":
    generate_sample()
