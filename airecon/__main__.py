from __future__ import annotations

import logging
import os
import sys


def main() -> None:
    host = os.getenv("AIRECON_HOST", "0.0.0.0")
    port = int(os.getenv("AIRECON_PORT", "8000"))
    log_level = os.getenv("AIRECON_LOG_LEVEL", "info").lower()

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    logger = logging.getLogger("airecon")
    logger.info("Starting AIRecon API on %s:%d", host, port)

    import uvicorn
    uvicorn.run(
        "airecon.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=log_level,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
