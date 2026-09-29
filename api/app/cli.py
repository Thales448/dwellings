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


def main() -> None:
    parser = argparse.ArgumentParser(prog="dwellings")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()


if __name__ == "__main__":
    main()
