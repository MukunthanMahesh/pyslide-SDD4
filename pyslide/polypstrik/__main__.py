# -*- coding: utf-8 -*-
""" CLI entry for ``python -m pyslide.polypstrik annotate|status``."""

from __future__ import annotations

import argparse
import json
import sys


def _build_parser():
    """ Build the annotate / status argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m pyslide.polypstrik",
        description="PolypStrik remote-annotation client",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="PolypStrik base URL (else POLYPSTRIK_BASE_URL)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Disable TLS certificate verification (local Docker)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="HTTP / upload timeout in seconds",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the result dict as JSON",
    )

    subparsers = parser.add_subparsers(dest="command")

    annotate_parser = subparsers.add_parser(
        "annotate",
        help="Upload (once) and/or check annotation status "
        "(.vsi auto-zips with companion folder)",
    )
    annotate_parser.add_argument("slide", help="Path to slide image")
    annotate_parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll until completed or failed",
    )
    annotate_parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between polls when --wait is set (default: 5)",
    )
    annotate_parser.add_argument(
        "--results-dir",
        default=None,
        help="Parent directory for downloads "
        "(default: ./polypstrik_results/<project_id>/)",
    )

    status_parser = subparsers.add_parser(
        "status", help="Check annotation status for a slide (no upload)"
    )
    status_parser.add_argument("slide", help="Path to slide image")

    return parser


def _print_result(result, *, as_json=False):
    """ Print annotate result as JSON or a short human summary."""
    if as_json:
        print(json.dumps(result, indent=2, default=str))
        return

    if result.get("message"):
        print(result["message"])
    print(f"project_id: {result.get('project_id')}")
    print(f"status:     {result.get('status')}")
    print(f"uploaded:   {result.get('uploaded')}")
    if result.get("results_dir"):
        print(f"results:    {result['results_dir']}")
    paths = result.get("paths") or []
    if paths:
        print("paths:")
        for p in paths:
            print(f"  {p}")


def main(argv=None):
    """ Run the PolypStrik CLI; return a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 1

    from .annotate import annotate_with_polypstrik

    common = {
        "base_url": args.base_url,
        "verify": not args.no_verify,
        "timeout": args.timeout,
    }

    if args.command == "annotate":
        result = annotate_with_polypstrik(
            args.slide,
            wait=args.wait,
            poll_interval=args.poll_interval,
            results_dir=args.results_dir,
            upload=True,
            **common,
        )
    elif args.command == "status":
        result = annotate_with_polypstrik(
            args.slide,
            wait=False,
            upload=False,
            **common,
        )
    else:
        parser.print_help()
        return 1

    _print_result(result, as_json=args.json)

    if result.get("project_id") is None and args.command == "status":
        return 2
    if result.get("status") == "failed":
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
