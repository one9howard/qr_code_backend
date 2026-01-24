
import os
import sys
from alembic.config import Config
from alembic import command
from dotenv import load_dotenv

# Load .env
load_dotenv(override=False)

# Fix URL
database_url = os.environ.get("DATABASE_URL", "")
if database_url.startswith("postgres://"):
    os.environ["DATABASE_URL"] = database_url.replace("postgres://", "postgresql://", 1)

# Run downgrade
alembic_cfg = Config("alembic.ini")
command.downgrade(alembic_cfg, "022")
print("Downgraded to 022")
