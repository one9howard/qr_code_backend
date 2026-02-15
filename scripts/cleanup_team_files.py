#!/usr/bin/env python3
import argparse
import logging

from app import create_app
from services.team_files import cleanup_expired_team_files


def main():
    parser = argparse.ArgumentParser(description="Delete expired team workspace files.")
    parser.add_argument("--dry-run", action="store_true", help="Show how many files would be deleted.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        deleted = cleanup_expired_team_files(dry_run=args.dry_run)
        mode = "dry-run" if args.dry_run else "deleted"
        logging.getLogger(__name__).info("[TeamFilesCleanup] mode=%s count=%s", mode, deleted)
        print(f"{mode}:{deleted}")


if __name__ == "__main__":
    main()
