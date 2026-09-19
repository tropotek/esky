import argparse
import sys

from esky.config import load_settings
from esky.auth import issue_token, token_issued_at
from esky.db.schema import SCHEMA_VERSION, migrate
from esky.profiles import InvalidProfileName, ProfileRegistry, UnknownProfile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="esky")
    sub = parser.add_subparsers(dest="command")

    profile = sub.add_parser("profile", help="manage memory profiles")
    psub = profile.add_subparsers(dest="subcommand")
    create = psub.add_parser("create", help="create a new profile database")
    create.add_argument("name")
    psub.add_parser("list", help="list existing profiles")
    p_migrate = psub.add_parser(
        "migrate", help="bring an existing profile database up to date")
    p_migrate.add_argument("name")

    token = sub.add_parser("token", help="manage profile access tokens")
    tsub = token.add_subparsers(dest="subcommand")
    t_issue = tsub.add_parser(
        "issue", help="issue a new token, invalidating any previous one")
    t_issue.add_argument("profile")
    t_status = tsub.add_parser(
        "status", help="show whether a token has been issued")
    t_status.add_argument("profile")

    sub.add_parser("serve", help="run the server")

    args = parser.parse_args(argv)
    settings = load_settings()
    registry = ProfileRegistry(settings.data_dir)

    if args.command == "profile":
        if args.subcommand == "create":
            try:
                path = registry.create(args.name)
            except InvalidProfileName:
                print(f"invalid profile name: {args.name!r}", file=sys.stderr)
                return 2
            print(f"created {path}")
            return 0
        if args.subcommand == "migrate":
            try:
                conn = registry.connect(args.name)
            except (UnknownProfile, InvalidProfileName):
                print(f"unknown profile: {args.name!r}", file=sys.stderr)
                return 2
            try:
                migrate(conn)
            finally:
                conn.close()
            print(f"migrated {args.name} to schema version {SCHEMA_VERSION}")
            return 0
        if args.subcommand == "list":
            for name in registry.list():
                print(name)
            return 0
        profile.print_help()
        return 2

    if args.command == "token":
        if args.subcommand in ("issue", "status"):
            try:
                conn = registry.connect(args.profile)
            except (UnknownProfile, InvalidProfileName):
                print(f"unknown profile: {args.profile!r}", file=sys.stderr)
                return 2
            try:
                if args.subcommand == "issue":
                    value = issue_token(conn)
                    print(f"token for {args.profile}: {value}")
                    print("Store it now — it is not recoverable, and issuing "
                          "again invalidates this one.")
                else:
                    issued = token_issued_at(conn)
                    print(f"{args.profile}: issued {issued}" if issued
                          else f"{args.profile}: no token issued (access denied)")
            finally:
                conn.close()
            return 0
        token.print_help()
        return 2

    if args.command == "serve":
        import uvicorn

        from esky.app import build_app

        uvicorn.run(build_app(settings), host=settings.host, port=settings.port)
        return 0

    parser.print_help()
    return 2
