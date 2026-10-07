import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    return cfg


def migrate() -> None:
    command.upgrade(_alembic_config(), "head")


def reset_link(email: str) -> None:
    from app.auth.service import issue_recovery_link

    url = issue_recovery_link(email)
    if url is None:
        raise SystemExit(f"no user for {email}")
    print(url)


def refresh_presentable() -> None:
    """Recompute is_presentable for every listing from current hunt criteria."""
    from sqlalchemy import select

    from app.core.db import session_scope
    from app.listings.models import Listing
    from app.listings.presentable import presentable
    from app.tenancy.models import Hunt

    updated = 0
    with session_scope() as db:
        hunts = {h.id: h for h in db.scalars(select(Hunt)).all()}
        for row in db.scalars(select(Listing)).all():
            hunt = hunts.get(row.hunt_id)
            if hunt is None:
                continue
            flag = presentable(hunt, row)
            if row.is_presentable != flag:
                row.is_presentable = flag
                updated += 1
    print(f"refreshed presentable flags; changed={updated}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="dwellings")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    sub.add_parser("refresh-presentable")
    admin = sub.add_parser("admin")
    admin_sub = admin.add_subparsers(dest="admin_command", required=True)
    reset = admin_sub.add_parser("reset-link")
    reset.add_argument("email")
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()
    elif args.command == "refresh-presentable":
        refresh_presentable()
    elif args.command == "admin" and args.admin_command == "reset-link":
        reset_link(args.email)


if __name__ == "__main__":
    main()
