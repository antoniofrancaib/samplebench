from __future__ import annotations

import argparse
import sys

from .generation import add_generate_parser
from .metrics import add_eval_parser


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lm-bench")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_generate_parser(subparsers)
    add_eval_parser(subparsers)
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

