"""`python -m legacy_roster` (or the exe): the window without arguments, the command line with."""
import sys


def main():
    if len(sys.argv) > 1:
        from .cli import main as run
    else:
        from .gui import main as run
    run()


if __name__ == '__main__':
    main()
