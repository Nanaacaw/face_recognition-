from __future__ import annotations

import argparse
import os

from src.settings.settings import load_settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=None)
    args = parser.parse_args()

    if args.config:
        os.environ["APP_CONFIG_PATH"] = args.config

    settings = load_settings(args.config)

    import uvicorn

    uvicorn.run(
        "src.frontend.main:app",
        host=settings.dashboard.host,
        port=settings.dashboard.port,
        reload=settings.dashboard.reload,
        reload_includes=["*.yaml", "configs/*.yaml"],
    )


if __name__ == "__main__":
    main()
