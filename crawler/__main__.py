"""CLI entrypoint for the on-demand markdown crawler."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from .paths import APP_DIR


def main() -> None:
    load_dotenv(APP_DIR / ".env")

    p = argparse.ArgumentParser(prog="python -m crawler")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_crawl = sub.add_parser("crawl", help="Crawl URLs and write markdown files")
    p_crawl.add_argument(
        "--settings",
        default="crawl-settings.json",
        help="Path to settings JSON (default: crawl-settings.json)",
    )
    p_crawl.add_argument(
        "--out",
        default="crawl-output",
        help="Output directory for markdown (default: crawl-output)",
    )
    p_crawl.set_defaults(func=_cmd_crawl)

    args = p.parse_args()
    args.func(args)


def _cmd_crawl(args: argparse.Namespace) -> None:
    from .md_crawler import run_from_settings_file

    run_from_settings_file(
        settings_path=Path(args.settings),
        out_dir=Path(args.out),
    )


if __name__ == "__main__":
    main()

