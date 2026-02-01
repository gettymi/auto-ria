import asyncio
import logging
import json
import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

import aiohttp
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.database import async_session, Car

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



@dataclass
class CarData:
    url: str
    title: str
    price_usd: int
    odometer: int
    username: str = "Unknown"
    phone_number: Optional[int] = None
    image_url: Optional[str] = None
    images_count: int = 0
    car_number: Optional[str] = None
    car_vin: Optional[str] = None


class AutoRiaScraper:
    def __init__(self):
        self.base_url = settings.BASE_URL
        self.search_url = settings.SEARCH_URL
        self.max_concurrent = settings.MAX_CONCURRENT_REQUESTS
        self.delay = settings.REQUEST_DELAY
        self.max_pages = settings.MAX_PAGES
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    async def fetch(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Fetch a page with rate limiting and error handling."""
        async with self.semaphore:
            try:
                await asyncio.sleep(self.delay)
                async with session.get(url, headers=self.headers, timeout=30) as response:
                    if response.status == 200:
                        return await response.text()
                    logger.warning(f"Got status {response.status} for {url}")
                    return None
            except asyncio.TimeoutError:
                logger.error(f"Timeout fetching {url}")
                return None
            except aiohttp.ClientError as e:
                logger.error(f"Error fetching {url}: {e}")
                return None

    async def fetch_json(self, session: aiohttp.ClientSession, url: str) -> Optional[dict]:
        """Fetch JSON data with rate limiting."""
        async with self.semaphore:
            try:
                await asyncio.sleep(self.delay)
                async with session.get(url, headers=self.headers, timeout=30) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
            except Exception as e:
                logger.error(f"Error fetching JSON {url}: {e}")
                return None

    async def post_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        json_body: dict,
        headers: Optional[dict] = None,
    ) -> Optional[dict]:
        """POST JSON with rate limiting and error handling."""
        async with self.semaphore:
            try:
                await asyncio.sleep(self.delay)
                async with session.post(
                    url,
                    json=json_body,
                    headers=headers or self.headers,
                    timeout=30,
                ) as response:
                    if response.status != 200:
                        body = await response.text()
                        logger.warning(
                            f"POST {url} status={response.status} body_head={body[:200]}"
                        )
                        return None
                    return await response.json()
            except Exception as e:
                logger.error(f"Error POST JSON {url}: {e}")
                return None

    def parse_list_page(self, html: str) -> list[str]:
        """
        Parse search results page and extract car URLs.
        
        Returns list of URLs to individual car pages.
        """
        soup = BeautifulSoup(html, "lxml")
        car_urls = []

        # AutoRia uses content-bar or ticket-item classes for car listings
        listings = soup.select("section.ticket-item")
        
        for listing in listings:
            link = listing.select_one("a.m-link-ticket")
            if link and link.get("href"):
                url = link["href"]
                if not url.startswith("http"):
                    url = self.base_url + url
                car_urls.append(url)

        logger.info(f"Found {len(car_urls)} cars on page")
        return car_urls

    def parse_detail_page(self, html: str, url: str) -> Optional[CarData]:
        """
        Parse individual car page and extract all data.
        
        Uses a hybrid approach:
        1. Extract structured data from embedded JSON (more reliable)
        2. Fall back to HTML parsing when needed
        """
        soup = BeautifulSoup(html, "lxml")

        try:
            # === Title (HTML) ===
            title = "Unknown"
            title_elem = soup.select_one("h1.titleL, h1.head, h1[class*='title']")
            if title_elem:
                title = title_elem.get_text(strip=True)
            if title == "Unknown":
                # Try page title
                page_title = soup.select_one("title")
                if page_title:
                    title_text = page_title.get_text(strip=True)
                    # Extract car name from "AUTO.RIA – Продам Форд Фьюжн 2019..."
                    match = re.search(r"Продам\s+(.+?)\s+\(", title_text)
                    if match:
                        title = match.group(1)

            # === Price USD (JSON) ===
            price_usd = 0
            # Look for price in embedded JSON - pattern: "priceValue":13600 or similar
            price_matches = re.findall(r'"price[A-Za-z]*":\s*(\d+)', html)
            for price in price_matches:
                p = int(price)
                # USD prices are typically 1000-500000
                if 1000 <= p <= 500000:
                    price_usd = p
                    break
            
            # Fallback: look in HTML
            if price_usd == 0:
                price_elem = soup.find(string=re.compile(r'\d+\s*\$'))
                if price_elem:
                    match = re.search(r'(\d[\d\s]*)\s*\$', price_elem)
                    if match:
                        price_usd = int(re.sub(r'\s', '', match.group(1)))

            # === Odometer (HTML + text search) ===
            odometer = 0
            # Look for "XX тис. км" pattern
            km_match = re.search(r'(\d+)\s*тис\.?\s*км', html)
            if km_match:
                odometer = int(km_match.group(1)) * 1000

            # === Seller username (JSON) ===
            username = "Unknown"
            seller_match = re.search(r'"name"\s*:\s*"([^"]+)"', html)
            if seller_match:
                username = seller_match.group(1)

            # === Main image URL (HTML) ===
            image_url = None
            image_elem = soup.select_one('img[src*="riastatic"]')
            if image_elem:
                image_url = image_elem.get("src")

            # === Images count (HTML) ===
            images = soup.select('img[src*="riastatic"]')
            images_count = len(images) if images else 1

            # === VIN code (JSON) ===
            car_vin = None
            vin_match = re.search(r'"vin"\s*:\s*"([A-HJ-NPR-Z0-9]{17})"', html, re.IGNORECASE)
            if vin_match:
                car_vin = vin_match.group(1).upper()

            # === Car number / plate (JSON) ===
            car_number = None
            plate_match = re.search(r'"plateNumber"\s*:\s*"([^"]+)"', html)
            if plate_match:
                car_number = plate_match.group(1)
            # Fallback: look in title
            if not car_number:
                plate_in_title = re.search(r'\(([A-Z]{2}\d{4}[A-Z]{2})\)', html)
                if plate_in_title:
                    car_number = plate_in_title.group(1)

            return CarData(
                url=url,
                title=title,
                price_usd=price_usd,
                odometer=odometer,
                username=username,
                image_url=image_url,
                images_count=images_count,
                car_number=car_number,
                car_vin=car_vin,
            )

        except Exception as e:
            logger.error(f"Error parsing {url}: {e}")
            return None

    def _extract_json_object(self, text: str, start_idx: int) -> Optional[str]:
        """
        Extract a JSON object substring starting at the first '{' at/after start_idx.
        Uses brace counting and string awareness.
        """
        obj_start = text.find("{", start_idx)
        if obj_start == -1:
            return None

        depth = 0
        in_string = False
        escape = False
        for i in range(obj_start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[obj_start : i + 1]

        return None

    def extract_phone_popup_payload(self, html: str) -> Optional[dict]:
        """
        Extract the payload for the phone popup BFF endpoint.

        The detail page contains a JSON config for the `autoPhone` button:
        `"id":"autoPhone" ... "actionData": { ... }`

        We POST that actionData to:
        `/bff/final-page/public/auto/popUp/`
        """
        idx = html.find('"id":"autoPhone"')
        if idx == -1:
            return None

        action_idx = html.find('"actionData":', idx)
        if action_idx == -1:
            return None

        obj = self._extract_json_object(html, action_idx)
        if not obj:
            return None

        try:
            return json.loads(obj)
        except Exception as e:
            logger.error(f"Failed to parse actionData JSON: {e}")
            return None

    def _extract_phone_from_popup_response(self, data: dict) -> Optional[int]:
        """Find phone number inside the popup response JSON."""
        try:
            raw = json.dumps(data, ensure_ascii=False)
        except Exception:
            raw = str(data)

        def normalize_ua_phone_digits(digits: str) -> Optional[int]:
            """
            Normalize to E.164-like Ukrainian format without '+' (e.g. 38063...).
            Accepts variants like:
            - 0XXXXXXXXX (10 digits) -> 380XXXXXXXXX
            - XXXXXXXXX (9 digits mobile code+number) -> 380XXXXXXXXX
            - 380XXXXXXXXX (12 digits) -> keep
            """
            if not digits:
                return None

            if digits.startswith("380") and len(digits) == 12:
                return int(digits)

            if digits.startswith("0") and len(digits) == 10:
                return int("38" + digits)

            # Sometimes the leading 0 is missing
            if len(digits) == 9 and digits[:2] in {
                "39",
                "50",
                "63",
                "66",
                "67",
                "68",
                "73",
                "91",
                "92",
                "93",
                "94",
                "95",
                "96",
                "97",
                "98",
                "99",
            }:
                return int("380" + digits)

            # Fallback: keep digits if they look like UA number length
            if len(digits) in (11, 12, 13) and digits.startswith("380"):
                return int(digits[:12])

            return None

        # Prefer tel: links (most reliable)
        tel_match = re.search(r"tel:\s*\(?\+?\d[\d\s\(\)-]{8,}", raw)
        if tel_match:
            digits = re.sub(r"[^\d]", "", tel_match.group(0))
            normalized = normalize_ua_phone_digits(digits)
            if normalized:
                return normalized

        # Fallback: formatted UA-like (0XX) XXX XX XX
        fmt = re.search(r"\(0\d{2}\)\s*\d{3}\s*\d{2}\s*\d{2}", raw)
        if fmt:
            digits = re.sub(r"[^\d]", "", fmt.group(0))
            normalized = normalize_ua_phone_digits(digits)
            if normalized:
                return normalized

        return None

    async def fetch_phone_number_via_popup(
        self,
        session: aiohttp.ClientSession,
        *,
        detail_url: str,
        payload: dict,
    ) -> Optional[int]:
        """
        Fetch seller phone number via BFF popup endpoint (works in browser).

        POST https://auto.ria.com/bff/final-page/public/auto/popUp/
        with the extracted `actionData` payload.
        """
        url = f"{self.base_url}/bff/final-page/public/auto/popUp/"
        headers = {
            **self.headers,
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Referer": detail_url,
            "X-RIA-Source": "vue3-1.41.10",
        }
        data = await self.post_json(session, url, json_body=payload, headers=headers)
        if not data:
            return None
        return self._extract_phone_from_popup_response(data)

    async def scrape_car(
        self, session: aiohttp.ClientSession, url: str
    ) -> Optional[CarData]:
        """
        Scrape a single car: detail page + phone number.
        """
        html = await self.fetch(session, url)
        if not html:
            return None

        car_data = self.parse_detail_page(html, url)
        if not car_data:
            return None

        # Try to get phone number via BFF popup endpoint
        payload = self.extract_phone_popup_payload(html)
        if payload:
            phone = await self.fetch_phone_number_via_popup(
                session, detail_url=url, payload=payload
            )
            car_data.phone_number = phone

        return car_data

    async def get_car_urls_from_page(
        self, session: aiohttp.ClientSession, page: int
    ) -> list[str]:
        """Fetch a single search results page and extract car URLs."""
        url = f"{self.search_url}?page={page}"
        html = await self.fetch(session, url)
        if not html:
            return []
        return self.parse_list_page(html)

    async def scrape_all(self) -> list[CarData]:
        """
        Main scraping method - List → Detail pattern.
        
        1. Scrape search result pages to get car URLs
        2. Scrape each car page for full details
        3. Fetch phone numbers where possible
        """
        logger.info(f"Starting scrape - max {self.max_pages} pages")
        all_cars: list[CarData] = []

        async with aiohttp.ClientSession() as session:
            # Phase 1: Get all car URLs from list pages
            logger.info("Phase 1: Collecting car URLs from search pages...")
            all_urls: list[str] = []

            for page in range(1, self.max_pages + 1):
                urls = await self.get_car_urls_from_page(session, page)
                if not urls:
                    logger.info(f"No more cars found at page {page}, stopping")
                    break
                all_urls.extend(urls)
                logger.info(f"Page {page}: found {len(urls)} cars (total: {len(all_urls)})")

            logger.info(f"Phase 1 complete: {len(all_urls)} car URLs collected")

            # Phase 2: Scrape each car page concurrently
            logger.info("Phase 2: Scraping individual car pages...")
            tasks = [self.scrape_car(session, url) for url in all_urls]
            results = await asyncio.gather(*tasks)

            all_cars = [car for car in results if car is not None]
            logger.info(f"Phase 2 complete: {len(all_cars)} cars scraped successfully")

        return all_cars

    async def save_cars(self, cars: list[CarData]) -> int:
        """
        Save cars to database using upsert (insert or update on conflict).
        
        Returns number of cars saved.
        """
        if not cars:
            return 0

        saved = 0
        async with async_session() as session:
            for car in cars:
                try:
                    # Use PostgreSQL upsert
                    stmt = insert(Car).values(
                        url=car.url,
                        title=car.title,
                        price_usd=car.price_usd,
                        odometer=car.odometer,
                        username=car.username,
                        phone_number=car.phone_number,
                        image_url=car.image_url,
                        images_count=car.images_count,
                        car_number=car.car_number,
                        car_vin=car.car_vin,
                        datetime_found=datetime.utcnow(),
                    )
                    
                    # On conflict (url already exists), update the record
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["url"],
                        set_={
                            "title": stmt.excluded.title,
                            "price_usd": stmt.excluded.price_usd,
                            "odometer": stmt.excluded.odometer,
                            "username": stmt.excluded.username,
                            "phone_number": stmt.excluded.phone_number,
                            "image_url": stmt.excluded.image_url,
                            "images_count": stmt.excluded.images_count,
                            "car_number": stmt.excluded.car_number,
                            "car_vin": stmt.excluded.car_vin,
                        },
                    )
                    
                    await session.execute(stmt)
                    saved += 1
                except Exception as e:
                    logger.error(f"Error saving car {car.url}: {e}")

            await session.commit()
            logger.info(f"Saved {saved} cars to database")

        return saved

    async def run(self) -> int:
        """
        Execute full scraping pipeline.
        
        Returns number of cars saved.
        """
        logger.info("=" * 50)
        logger.info("AutoRia Scraper - Starting run")
        logger.info("=" * 50)

        cars = await self.scrape_all()
        saved = await self.save_cars(cars)

        logger.info("=" * 50)
        logger.info(f"Scraping complete: {saved} cars saved")
        logger.info("=" * 50)

        return saved


async def run_scraper() -> int:
    """Entry point for the scraper."""
    scraper = AutoRiaScraper()
    return await scraper.run()
