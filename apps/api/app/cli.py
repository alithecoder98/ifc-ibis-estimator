"""Small CLI for one-off admin tasks.

Usage (from apps/api):
    uv run python -m app.cli seed-admin --email admin@example.com --password <password>

Idempotent: if the email already exists, it's promoted to admin and its password is
reset to the one given (useful for recovering access, not just first-time setup).
"""

import argparse

from app.core.security import hash_password
from app.db.models import User
from app.db.session import SessionLocal


def seed_admin(email: str, password: str) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                email=email, password_hash=hash_password(password), role="admin"
            )
            db.add(user)
            db.commit()
            print(f"Created admin user: {email}")
        else:
            user.role = "admin"
            user.password_hash = hash_password(password)
            db.commit()
            print(f"Updated existing user to admin and reset password: {email}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_admin_parser = subparsers.add_parser(
        "seed-admin", help="Create or promote the first admin user"
    )
    seed_admin_parser.add_argument("--email", required=True)
    seed_admin_parser.add_argument("--password", required=True)

    args = parser.parse_args()
    if args.command == "seed-admin":
        seed_admin(args.email, args.password)


if __name__ == "__main__":
    main()
