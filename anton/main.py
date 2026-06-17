from .cli import App


def cli_entry():
    app = App()
    app.run()


if __name__ == "__main__":
    cli_entry()
