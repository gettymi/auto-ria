import asyncio
import logging
import signal
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
UA_TIMEZONE = ZoneInfo("Europe/Kyiv")
from app.database import init_db
from app.scraper import run_scraper
from app.utils import create_dump, cleanup_old_dumps

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


class ScraperService:
    """
    Main service that manages the scraper lifecycle.
    
    Handles:
    - Database initialization
    - Scheduled scraping
    - Daily database dumps
    - Graceful shutdown
    """

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.running = True

    async def scrape_job(self):
        """Job executed by scheduler to run the scraper."""
        logger.info("Scheduled scrape job starting...")
        try:
            count = await run_scraper()
            logger.info(f"Scheduled scrape completed: {count} cars")
        except Exception as e:
            logger.error(f"Scheduled scrape failed: {e}")

    async def dump_job(self):
        """Job executed by scheduler to create database dump."""
        logger.info("Scheduled dump job starting...")
        try:
            dump_path = await create_dump()
            if dump_path:
                logger.info(f"Dump created: {dump_path}")
                # Cleanup old dumps (keep last 7)
                await cleanup_old_dumps(keep_count=7)
            else:
                logger.warning("Dump creation returned no path")
        except Exception as e:
            logger.error(f"Scheduled dump failed: {e}")

    def setup_scheduler(self):
        """Configure APScheduler with scrape and dump jobs."""
        
        # Parse RUN_TIME (format: "HH:MM")
        run_hour, run_minute = map(int, settings.RUN_TIME.split(":"))
        dump_hour, dump_minute = map(int, settings.DUMP_TIME.split(":"))
        
        # Scraping job - runs daily at specified UA time
        self.scheduler.add_job(
            self.scrape_job,
            CronTrigger(hour=run_hour, minute=run_minute, timezone=UA_TIMEZONE),
            id="scrape_job",
            name="AutoRia Scraper",
            replace_existing=True,
        )
        logger.info(f"Scrape job scheduled: daily at {settings.RUN_TIME} UA time (Europe/Kyiv)")

        # Dump job - runs daily at configured UA time
        self.scheduler.add_job(
            self.dump_job,
            CronTrigger(hour=dump_hour, minute=dump_minute, timezone=UA_TIMEZONE),
            id="dump_job",
            name="Database Dump",
            replace_existing=True,
        )
        logger.info(f"Dump job scheduled: daily at {settings.DUMP_TIME} UA time (Europe/Kyiv)")

        self.scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self, signum=None, frame=None):
        """Graceful shutdown handler."""
        logger.info("Shutdown signal received...")
        self.running = False
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    async def run(self):
        """
        Main run loop.
        
        1. Initialize database
        2. Run initial scrape
        3. Start scheduler
        4. Wait for shutdown
        """
        logger.info("=" * 60)
        logger.info("AutoRia Scraper Service Starting")
        logger.info(f"Scheduled run time: {settings.RUN_TIME} UA time (Europe/Kyiv)")
        logger.info(f"Max pages: {settings.MAX_PAGES}")
        logger.info(f"Max concurrent: {settings.MAX_CONCURRENT_REQUESTS}")
        logger.info("=" * 60)

        # Initialize database
        logger.info("Initializing database...")
        await init_db()
        logger.info("Database initialized")

        # Run initial scrape
        logger.info("Running initial scrape...")
        try:
            count = await run_scraper()
            logger.info(f"Initial scrape completed: {count} cars")
        except Exception as e:
            logger.error(f"Initial scrape failed: {e}")

        # Setup and start scheduler
        self.setup_scheduler()

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        # Keep running until shutdown
        logger.info("Service running. Press Ctrl+C to stop.")
        while self.running:
            await asyncio.sleep(1)

        logger.info("Service stopped")


async def main():
    """Entry point."""
    service = ScraperService()
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
