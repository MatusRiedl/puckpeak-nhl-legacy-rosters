"""`python -m legacy_roster` (or the exe): the window without arguments, the command line with.
`--classic` opens the old window (kept for 0.10.x, also used by itself when the new one cannot start)."""
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1:] != ['--classic']:
        from .cli import main as run
    else:
        from .window.main import main as run
    run()


if __name__ == '__main__':
    main()
