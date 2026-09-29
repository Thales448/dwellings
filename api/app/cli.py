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


def main() -> None:
    parser = argparse.ArgumentParser(prog="dwellings")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    admin = sub.add_parser("admin")
    admin_sub = admin.add_subparsers(dest="admin_command", required=True)
    reset = admin_sub.add_parser("reset-link")
    reset.add_argument("email")
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()
    elif args.command == "admin" and args.admin_command == "reset-link":
        reset_link(args.email)


if __name__ == "__main__":
    main()
