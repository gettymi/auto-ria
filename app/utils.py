import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

DUMPS_DIR = Path("/dumps") if os.path.exists("/dumps") else Path("dumps")


async def create_dump() -> Optional[str]:
    DUMPS_DIR.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_filename = f"autoria_dump_{timestamp}.sql"
    dump_path = DUMPS_DIR / dump_filename
    
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.POSTGRES_PASSWORD
    
    cmd = [
        "pg_dump",
        "-h", settings.POSTGRES_HOST,
        "-p", str(settings.POSTGRES_PORT),
        "-U", settings.POSTGRES_USER,
        "-d", settings.POSTGRES_DB,
        "-f", str(dump_path),
        "--no-owner",
        "--no-acl",
    ]
    
    logger.info(f"Creating database dump: {dump_path}")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            # Get file size
            size_mb = dump_path.stat().st_size / (1024 * 1024)
            logger.info(f"Dump created successfully: {dump_path} ({size_mb:.2f} MB)")
            return str(dump_path)
        else:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error(f"pg_dump failed: {error_msg}")
            return None
            
    except FileNotFoundError:
        logger.error("pg_dump not found. Is postgresql-client installed?")
        return None
    except Exception as e:
        logger.error(f"Error creating dump: {e}")
        return None


async def cleanup_old_dumps(keep_count: int = 7) -> int:
    """
    Remove old database dumps, keeping only the most recent ones.
    
    Args:
        keep_count: Number of recent dumps to keep
        
    Returns:
        Number of dumps deleted
    """
    if not DUMPS_DIR.exists():
        return 0
    
    # Get all dump files sorted by modification time (newest first)
    dump_files = sorted(
        DUMPS_DIR.glob("autoria_dump_*.sql"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    
    # Keep the most recent ones, delete the rest
    files_to_delete = dump_files[keep_count:]
    deleted = 0
    
    for dump_file in files_to_delete:
        try:
            dump_file.unlink()
            logger.info(f"Deleted old dump: {dump_file}")
            deleted += 1
        except Exception as e:
            logger.error(f"Error deleting {dump_file}: {e}")
    
    if deleted:
        logger.info(f"Cleaned up {deleted} old dumps, kept {keep_count}")
    
    return deleted


def format_phone(phone: Optional[int]) -> str:
    """Format phone number for display."""
    if not phone:
        return "N/A"
    
    phone_str = str(phone)
    
    # Ukrainian format: +38 (0XX) XXX-XX-XX
    if len(phone_str) == 12 and phone_str.startswith("380"):
        return f"+{phone_str[:2]} ({phone_str[2:5]}) {phone_str[5:8]}-{phone_str[8:10]}-{phone_str[10:]}"
    
    return phone_str


def format_price(price: int) -> str:
    """Format price with thousand separators."""
    return f"${price:,}"


def format_odometer(km: int) -> str:
    """Format odometer reading."""
    return f"{km:,} km"


async def get_stats() -> dict:
    """
    Get scraper statistics from the database.
    
    Returns dict with counts and summaries.
    """
    from app.database import async_session, Car
    from sqlalchemy import func, select
    
    async with async_session() as session:
        # Total cars
        total = await session.scalar(select(func.count(Car.id)))
        
        # Cars with VIN
        with_vin = await session.scalar(
            select(func.count(Car.id)).where(Car.car_vin.isnot(None))
        )
        
        # Cars with phone
        with_phone = await session.scalar(
            select(func.count(Car.id)).where(Car.phone_number.isnot(None))
        )
        
        # Average price
        avg_price = await session.scalar(select(func.avg(Car.price_usd)))
        
        # Price range
        min_price = await session.scalar(select(func.min(Car.price_usd)))
        max_price = await session.scalar(select(func.max(Car.price_usd)))
        
        return {
            "total_cars": total or 0,
            "cars_with_vin": with_vin or 0,
            "cars_with_phone": with_phone or 0,
            "average_price": int(avg_price) if avg_price else 0,
            "min_price": min_price or 0,
            "max_price": max_price or 0,
        }


def print_stats(stats: dict) -> None:
    """Print statistics in a formatted way."""
    print("\n" + "=" * 40)
    print("AutoRia Scraper Statistics")
    print("=" * 40)
    print(f"Total cars:      {stats['total_cars']:,}")
    print(f"With VIN:        {stats['cars_with_vin']:,}")
    print(f"With phone:      {stats['cars_with_phone']:,}")
    print(f"Average price:   {format_price(stats['average_price'])}")
    print(f"Price range:     {format_price(stats['min_price'])} - {format_price(stats['max_price'])}")
    print("=" * 40 + "\n")
