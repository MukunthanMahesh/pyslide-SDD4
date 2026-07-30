# -*- coding: utf-8 -*-

import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m pyslide.polypstrik",
        description="PolypStrik remote-annotation client",
    )
    subparsers = parser.add_subparsers(dest="command")

    annotate_parser = subparsers.add_parser(
        "annotate", help="Upload (once) and/or check annotation status"
    )
    annotate_parser.add_argument("slide", help="Path to slide image")

    status_parser = subparsers.add_parser(
        "status", help="Check annotation status for a slide"
    )
    status_parser.add_argument("slide", help="Path to slide image")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 1

    print("not implemented")
    return 1


if __name__ == "__main__":
    sys.exit(main())
