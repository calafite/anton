import argparse
from .cli import App


def cli_entry():
    parser = argparse.ArgumentParser(description="Anton: Remote Audio Caller")
    subparsers = parser.add_subparsers(dest="command")
    
    subparsers.add_parser("config", help="Run interactive configuration")
    
    args = parser.parse_args()
    
    app = App()
    if args.command == "config":
        app.configure()
    else:
        app.run()


if __name__ == "__main__":
    cli_entry()
