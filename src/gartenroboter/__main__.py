"""Main entry point for Gartenroboter3000."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from gartenroboter.app import main as app_main


def setup_logging(debug: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if debug else logging.INFO

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    # File handler
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    file_handler = logging.FileHandler(
        log_dir / "gartenroboter.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)  # Always log debug to file

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="gartenroboter",
        description="Gartenroboter3000 - Raspberry Pi Garden Automation System",
    )

    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Path to configuration file (default: config.json)",
    )

    parser.add_argument(
        "-m",
        "--mock",
        action="store_true",
        help="Use mock GPIO for development (no real hardware)",
    )

    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Setup logging
    setup_logging(debug=args.debug)

    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Gartenroboter3000 Starting")
    logger.info("=" * 60)
    logger.info(f"Config: {args.config}")
    logger.info(f"Mock mode: {args.mock}")
    logger.info(f"Debug: {args.debug}")

    try:
        # Run the async application
        asyncio.run(
            app_main(
                config_path=args.config,
                mock_mode=args.mock,
            )
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Gartenroboter3000 stopped")


if __name__ == "__main__":
    main()
