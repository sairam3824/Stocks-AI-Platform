from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
from pathlib import Path

from .config import load_config
from .publish import publish_latest
from .run_portfolio import run as run_portfolio


def serve(directory: Path, port: int) -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Serving {directory} at http://localhost:{port}/index.html")
        httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run forecast and serve local site")
    parser.add_argument(
        "--config",
        default="config/portfolio.json",
        help="Path to portfolio config JSON",
    )
    parser.add_argument("--port", type=int, default=8000, help="Port for local server")
    args = parser.parse_args()

    config_path = Path(args.config)
    run_portfolio(config_path)
    publish_latest(config_path)

    config = load_config(config_path)
    serve(config.publish_dir, args.port)


if __name__ == "__main__":
    main()
