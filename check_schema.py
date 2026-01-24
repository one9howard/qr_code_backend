
from database import get_db
from app import create_app
import sqlalchemy as sa

app = create_app()

with app.app_context():
    db = get_db()
    rows = db.execute("SELECT column_name, is_nullable, column_default FROM information_schema.columns WHERE table_name='qr_variants'").fetchall()
    print("qr_variants columns:")
    for r in rows:
        print(f"{r[0]}")
