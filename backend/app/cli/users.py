"""User administration from the command line (roles are never self-assigned).

    python -m app.cli.users list
    python -m app.cli.users set-role someone@example.com admin

The user must have signed in at least once so their profile exists.
"""

import argparse
import sys
from typing import get_args

from sqlalchemy import func, select

from app.db.session import get_sessionmaker
from app.models import User
from app.models.enums import UserRole


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage AGRI-SENSE users.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list users")
    sr = sub.add_parser("set-role", help="change a user's role")
    sr.add_argument("email")
    sr.add_argument("role", choices=get_args(UserRole))
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        if args.cmd == "list":
            for u in db.scalars(select(User).order_by(User.created_at)):
                print(f"{u.email:40} {u.role:11} {u.id}")
            return 0
        user = db.scalar(select(User).where(func.lower(User.email) == args.email.lower()))
        if user is None:
            print(f"No user {args.email!r}. They must sign in once first.", file=sys.stderr)
            return 1
        user.role = args.role
        db.commit()
        print(f"{user.email} is now {user.role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
