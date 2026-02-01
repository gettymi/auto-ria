import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.scraper import AutoRiaScraper, CarData


# Sample HTML for testing
SAMPLE_LIST_HTML = """
<html>
<body>
    <section class="ticket-item">
        <a class="m-link-ticket" href="/uk/auto_toyota_camry_12345.html">Toyota Camry</a>
    </section>
    <section class="ticket-item">
        <a class="m-link-ticket" href="/uk/auto_honda_accord_67890.html">Honda Accord</a>
    </section>
</body>
</html>
"""

SAMPLE_DETAIL_HTML = """
<html>
<body>
    <h1 class="head">Toyota Camry 2020</h1>
    <div class="price_value"><strong>25 000 $</strong></div>
    <div class="base-information">
        <span class="size18">45 тис. км</span>
    </div>
    <div class="seller_info_name">
        <a href="/user/123">Іван Петренко</a>
    </div>
    <img class="outline" src="https://cdn.riastatic.com/photos/auto/123.jpg"/>
    <span class="label-vin">JTDKN3DU5A0123456</span>
    <span class="state-num">AA1234BB</span>
    <script>
        var autoId = 12345;
        var hash = "abc123def456";
    </script>
</body>
</html>
"""


class TestAutoRiaScraper:
    """Test suite for AutoRiaScraper."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scraper = AutoRiaScraper()

    def test_parse_list_page(self):
        """Test parsing of search results page."""
        urls = self.scraper.parse_list_page(SAMPLE_LIST_HTML)
        
        assert len(urls) == 2
        assert "toyota_camry_12345" in urls[0]
        assert "honda_accord_67890" in urls[1]

    def test_parse_detail_page(self):
        """Test parsing of individual car page."""
        url = "https://auto.ria.com/uk/auto_toyota_camry_12345.html"
        car = self.scraper.parse_detail_page(SAMPLE_DETAIL_HTML, url)
        
        assert car is not None
        assert car.title == "Toyota Camry 2020"
        assert car.price_usd == 25000
        assert car.odometer == 45000  # 45 тис. km = 45000
        assert car.username == "Іван Петренко"
        assert car.car_vin == "JTDKN3DU5A0123456"
        assert car.car_number == "AA1234BB"
        assert "cdn.riastatic.com" in car.image_url

    def test_extract_phone_data(self):
        """Test extraction of phone API parameters."""
        auto_id, hash_value = self.scraper.extract_phone_data(SAMPLE_DETAIL_HTML)
        
        assert auto_id == "12345"
        assert hash_value == "abc123def456"

    def test_parse_empty_list_page(self):
        """Test handling of empty list page."""
        empty_html = "<html><body></body></html>"
        urls = self.scraper.parse_list_page(empty_html)
        
        assert len(urls) == 0

    def test_car_data_dataclass(self):
        """Test CarData dataclass creation."""
        car = CarData(
            url="https://example.com/car/1",
            title="Test Car",
            price_usd=10000,
            odometer=50000,
        )
        
        assert car.url == "https://example.com/car/1"
        assert car.username == "Unknown"  # Default value
        assert car.phone_number is None  # Optional field


class TestAsyncOperations:
    """Async-ish smoke checks (kept minimal, no pytest dependency)."""

    def test_scraper_initialization(self):
        scraper = AutoRiaScraper()
        assert scraper.base_url == "https://auto.ria.com"


def test_integration_parse_flow():
    """Integration test for the full parse flow."""
    scraper = AutoRiaScraper()
    
    # Parse list page
    urls = scraper.parse_list_page(SAMPLE_LIST_HTML)
    assert len(urls) > 0
    
    # Parse detail page
    car = scraper.parse_detail_page(SAMPLE_DETAIL_HTML, urls[0])
    assert car is not None
    assert car.price_usd > 0
    
    # Extract phone data
    auto_id, hash_val = scraper.extract_phone_data(SAMPLE_DETAIL_HTML)
    assert auto_id is not None


if __name__ == "__main__":
    # Run basic tests without pytest
    print("Running basic tests...")
    
    scraper = AutoRiaScraper()
    
    # Test 1: List parsing
    urls = scraper.parse_list_page(SAMPLE_LIST_HTML)
    assert len(urls) == 2, f"Expected 2 URLs, got {len(urls)}"
    print("✓ List parsing works")
    
    # Test 2: Detail parsing
    car = scraper.parse_detail_page(SAMPLE_DETAIL_HTML, urls[0])
    assert car is not None, "Car parsing failed"
    assert car.price_usd == 25000, f"Expected 25000, got {car.price_usd}"
    print("✓ Detail parsing works")
    
    # Test 3: Phone data extraction
    auto_id, hash_val = scraper.extract_phone_data(SAMPLE_DETAIL_HTML)
    assert auto_id == "12345", f"Expected 12345, got {auto_id}"
    print("✓ Phone data extraction works")
    
    print("\nAll tests passed! ✓")
