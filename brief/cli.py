"""CLI: python -m brief run [--send] | portfolio add|remove|show | serve"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from .config import portfolio_path, write_yaml
from .schemas import Position


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="brief")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="generate a brief (and optionally email it)")
    r.add_argument("--send", action="store_true")

    p = sub.add_parser("portfolio", help="manage config/portfolio.yaml")
    ps = p.add_subparsers(dest="pcmd", required=True)
    ps.add_parser("show")
    a = ps.add_parser("add")
    a.add_argument("ticker"); a.add_argument("shares", type=float); a.add_argument("--cost", type=float); a.add_argument("--note")
    d = ps.add_parser("remove"); d.add_argument("ticker")

    s = sub.add_parser("serve", help="run the FastAPI service")
    s.add_argument("--port", type=int, default=8000)

    args = ap.parse_args(argv)
    if args.cmd == "run":
        from . import pipeline
        res = pipeline.run(send=args.send)
        print(f"{res.brief.headline}\n{res.reading_minutes} min read, sent={res.sent}")
        print(res.text if not args.send else "")
        return 0
    if args.cmd == "portfolio":
        from . import pipeline
        pf = pipeline.load_portfolio()
        if args.pcmd == "add":
            pos = Position(ticker=args.ticker, shares=args.shares, cost_basis=args.cost, note=args.note)
            pf.positions = [x for x in pf.positions if x.ticker != pos.ticker] + [pos]
            write_yaml(portfolio_path(), pf.model_dump())
        elif args.pcmd == "remove":
            pf.positions = [x for x in pf.positions if x.ticker != args.ticker.upper()]
            write_yaml(portfolio_path(), pf.model_dump())
        for x in pf.positions:
            print(f"{x.ticker:8} {x.shares:>10g} @ {x.cost_basis if x.cost_basis is not None else 'n/a'}")
        return 0
    if args.cmd == "serve":
        import uvicorn
        uvicorn.run("brief.api:app", host="0.0.0.0", port=args.port)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
