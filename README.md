# 🚗 AutoRia Scraper

A high-performance, production-grade asynchronous scraper for [auto.ria.com](https://auto.ria.com) - Ukraine's largest car marketplace.

## ✨ Features

- **Async Architecture**: Uses `aiohttp` for concurrent HTTP requests
- **List → Detail Pattern**: Efficiently collects all car data including VIN, images, and seller info
- **Phone Number Extraction**: Fetches seller phone numbers via AutoRia's internal API
- **PostgreSQL Storage**: SQLAlchemy 2.0 with async support and Pydantic validation
- **Scheduled Scraping**: APScheduler for automated periodic data collection
- **Daily Backups**: Automatic database dumps with retention policy
- **Docker Ready**: Fully containerized with docker-compose

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                              │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│   │  APScheduler │───▶│   Scraper   │───▶│  Database   │    │
│   │  (cron jobs) │    │  (aiohttp)  │    │  (asyncpg)  │    │
│   └─────────────┘    └─────────────┘    └─────────────┘    │
│         │                                      │            │
│         ▼                                      ▼            │
│   ┌─────────────┐                       ┌─────────────┐    │
│   │  Daily Dump │                       │  PostgreSQL │    │
│   │  (pg_dump)  │                       │   (Docker)  │    │
│   └─────────────┘                       └─────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 📊 Data Collected

| Field | Description |
|-------|-------------|
| `url` | Unique car listing URL |
| `title` | Car title (make, model, year) |
| `price_usd` | Price in USD |
| `odometer` | Mileage in kilometers |
| `username` | Seller's name |
| `phone_number` | Seller's phone number |
| `image_url` | Main image URL |
| `images_count` | Total number of images |
| `car_number` | License plate number |
| `car_vin` | Vehicle Identification Number |
| `datetime_found` | Timestamp when scraped |

## 🚀 Quick Start

### 1. Configure `.env`

```bash
cd auto-ria

# Create .env (it is gitignored)
cat > .env << 'EOF'
POSTGRES_USER=autoria
POSTGRES_PASSWORD=your_password
POSTGRES_DB=autoria_db
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Daily schedules (UA time, Europe/Kyiv)
RUN_TIME=12:00
DUMP_TIME=12:00

# Scraper performance / limits
MAX_CONCURRENT_REQUESTS=5
REQUEST_DELAY=1.0
MAX_PAGES=10
EOF
```

### 2. Run with Docker (Recommended)

```bash
# Build and start services
docker-compose up --build

# Or run in background
docker-compose up -d --build

# View logs
docker-compose logs -f app
```

## ✅ Proof it works (quick checks)

Run one scraping cycle now (does list → detail → phone → save):

```bash
docker-compose run --rm app python -c "import asyncio; from app.scraper import run_scraper; print(asyncio.run(run_scraper()))"
```

Check that data is in PostgreSQL and phones are present:

```bash
docker-compose exec db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) total, count(phone_number) phones from cars;"'
```

Create a dump now and verify it appears in `dumps/`:

```bash
docker-compose run --rm app python -c "import asyncio; from app.utils import create_dump; print(asyncio.run(create_dump()))"
ls -lh dumps/
```

**Note**: SQL dumps are **not committed** to Git (they may contain scraped personal data and become very large). The repo keeps only `dumps/.gitkeep`.

### 3. Run Locally (Development)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL (via Docker or locally)
docker-compose up -d db

# Set local host
export POSTGRES_HOST=localhost

# Run the scraper
python -m app.main
```

## ⚙️ Configuration

All configuration is done via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | - | Database username |
| `POSTGRES_PASSWORD` | - | Database password |
| `POSTGRES_DB` | - | Database name |
| `POSTGRES_HOST` | `db` | Database host |
| `POSTGRES_PORT` | `5432` | Database port |
| `RUN_TIME` | `12:00` | Daily scrape time in **UA timezone** (Europe/Kyiv) |
| `DUMP_TIME` | `12:00` | Daily DB dump time in **UA timezone** (Europe/Kyiv) |
| `MAX_CONCURRENT_REQUESTS` | `5` | Concurrent HTTP requests |
| `REQUEST_DELAY` | `1.0` | Delay between requests (seconds) |
| `MAX_PAGES` | `10` | Max search result pages to scrape |

## 📁 Project Structure

```
auto-ria/
├── app/
│   ├── __init__.py
│   ├── config.py       # Pydantic settings
│   ├── database.py     # SQLAlchemy models
│   ├── main.py         # Entry point + scheduler
│   ├── scraper.py      # Core scraping logic
│   └── utils.py        # Dump + helper functions
├── dumps/              # Database backups
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## 🔄 Scraping Flow

1. **List Phase**: Fetch search result pages, extract car URLs
2. **Detail Phase**: For each URL, fetch the car page
3. **Parse Phase**: Extract all data fields using BeautifulSoup
4. **Phone Phase**: Fetch seller phone numbers via AutoRia **BFF popup** endpoint (`/bff/final-page/public/auto/popUp/`)
5. **Save Phase**: Upsert to PostgreSQL (insert or update existing)

## 💾 Database Dumps

Dumps are created daily at `DUMP_TIME` (UA time) and stored in the `dumps/` directory (project root).

```bash
# Create a dump now (recommended way)
docker-compose run --rm app python -c "import asyncio; from app.utils import create_dump; print(asyncio.run(create_dump()))"

# List dumps
ls -lh dumps/

# Preview a dump
head -n 30 dumps/autoria_dump_*.sql
```

## 📈 Monitoring

View scraper statistics:

```python
from app.utils import get_stats, print_stats
import asyncio

stats = asyncio.run(get_stats())
print_stats(stats)
```

## 🛡️ Rate Limiting

The scraper is configured to be respectful:

- **Semaphore**: Limits concurrent requests (default: 5)
- **Delay**: Waits between requests (default: 1 second)
- **User-Agent**: Uses realistic browser headers

If you see `429 Too Many Requests` in logs, reduce `MAX_CONCURRENT_REQUESTS` or increase `REQUEST_DELAY`.

## 🐳 Docker Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f

# Access database
docker-compose exec db psql -U autoria autoria_db

# Rebuild after changes
docker-compose up --build
```

## 📝 License

MIT
