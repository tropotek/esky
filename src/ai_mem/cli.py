import argparse
import sys

from ai_mem.config import load_settings
from ai_mem.profiles import InvalidProfileName, ProfileRegistry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai-mem")
    sub = parser.add_subparsers(dest="command")

    profile = sub.add_parser("profile", help="manage memory profiles")
    psub = profile.add_subparsers(dest="subcommand")
    create = psub.add_parser("create", help="create a new profile database")
    create.add_argument("name")
    psub.add_parser("list", help="list existing profiles")

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
        if args.subcommand == "list":
            for name in registry.list():
                print(name)
            return 0
        profile.print_help()
        return 2

    if args.command == "serve":
        import uvicorn

        from ai_mem.app import build_app

        uvicorn.run(build_app(settings), host=settings.host, port=settings.port)
        return 0

    parser.print_help()
    return 2
