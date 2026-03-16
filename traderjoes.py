#!/usr/bin/env python3
"""
Trader Joe's Price Tracking - Python Implementation
Fetches product prices from Trader Joe's GraphQL API and stores in SQLite.
"""

import argparse
import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Optional

import requests

# Optional Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


class TraderJoesAPI:
    """Handler for Trader Joe's GraphQL API interactions."""

    BASE_URL = "https://www.traderjoes.com/api/graphql"

    # Base headers for requests (Cookie will be added dynamically)
    BASE_HEADERS = {
        "sec-ch-ua-platform": '"macOS"',
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "accept": "*/*",
        "sec-ch-ua": '"Chromium";v="145", "Not:A-Brand";v="99"',
        "content-type": "application/json",
        "sec-ch-ua-mobile": "?0",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "host": "www.traderjoes.com",
    }

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update(self.BASE_HEADERS)
        self._initialize_session()

    def _log(self, message: str):
        if self.verbose:
            print(message)

    def _get_selenium_cookie(self):
        """Get affinity cookie using Selenium (automated browser)."""
        if not SELENIUM_AVAILABLE:
            return None

        try:
            self._log("🤖 Using automated browser to get fresh cookie...")

            # Setup Chrome options
            options = Options()
            options.add_argument('--headless')  # Run in background
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920x1080')
            options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36')

            # Setup webdriver
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)

            try:
                # Visit the product page that sets the affinity cookie
                driver.get('https://www.traderjoes.com/home/products')

                # Wait a moment for page to load
                time.sleep(2)

                # Get the affinity cookie
                affinity_cookie = driver.get_cookie('affinity')

                if affinity_cookie:
                    cookie_value = affinity_cookie['value']
                    self._log(f"✅ Got fresh Selenium cookie: {cookie_value}")
                    return cookie_value
                else:
                    self._log("⚠️  No affinity cookie found via Selenium")
                    return None

            finally:
                driver.quit()

        except Exception as e:
            self._log(f"⚠️  Selenium cookie retrieval failed: {e}")
            return None

    def _initialize_session(self):
        """Initialize session with fallback cookie first."""
        fallback_cookie = os.getenv("TJ_AFFINITY_COOKIE", "6e56efa815f07aa2")
        self._log("Initializing session with Trader Joe's...")

        # Start with fast fallback approach
        self._log("📋 Using fallback cookie (Selenium available if needed)")
        self.session.cookies.set('affinity', fallback_cookie)

    def _refresh_cookie_with_selenium(self):
        """Refresh cookie using Selenium when fallback fails."""
        if not SELENIUM_AVAILABLE:
            self._log("⚠️  Selenium not available for cookie refresh")
            return False

        selenium_cookie = self._get_selenium_cookie()
        if selenium_cookie:
            self.session.cookies.set('affinity', selenium_cookie)
            return True
        return False

    def _make_request_with_retry(self, method, url, **kwargs):
        """Make request with automatic cookie refresh on 403."""
        try:
            response = getattr(self.session, method)(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                self._log("🔄 Got 403 error, refreshing cookie with Selenium...")
                if self._refresh_cookie_with_selenium():
                    self._log("🔄 Retrying with fresh cookie...")
                    response = getattr(self.session, method)(url, **kwargs)
                    response.raise_for_status()
                    return response
                else:
                    self._log("❌ Cookie refresh failed")
            raise

    def fetch_products_by_store(self, store_code: str, page: int = 1, page_size: int = 100) -> Optional[Dict]:
        """Fetch products for a specific store and page."""
        query = """
        query SearchProducts($pageSize: Int, $currentPage: Int, $storeCode: String, $published: String = "1") {
          products(
            filter: {store_code: {eq: $storeCode}, published: {eq: $published}}
            pageSize: $pageSize
            currentPage: $currentPage
          ) {
            items {
              sku
              url_key
              name
              item_title
              item_description
              sales_size
              sales_uom_description
              country_of_origin
              availability
              new_product
              promotion
              retail_price
              created_at
              updated_at
              __typename
            }
            total_count
            page_info {
              current_page
              page_size
              total_pages
              __typename
            }
            __typename
          }
        }
        """

        payload = {
            "operationName": "SearchProducts",
            "variables": {
                "storeCode": store_code,
                "published": "1",
                "currentPage": page,
                "pageSize": page_size
            },
            "query": query
        }

        try:
            response = self._make_request_with_retry('post', self.BASE_URL, json=payload)
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching page {page} for store {store_code}: {e}")
            return None

    def search_products(self, store_code: str, search_term: str) -> Optional[Dict]:
        """Search for products by name/description."""
        query = """
        query SearchProducts($search: String, $pageSize: Int, $currentPage: Int, $storeCode: String = "226", $availability: String = "1", $published: String = "1") {
          products(
            search: $search
            filter: {store_code: {eq: $storeCode}, published: {eq: $published}, availability: {match: $availability}}
            pageSize: $pageSize
            currentPage: $currentPage
          ) {
            items {
              sku
              url_key
              name
              item_title
              item_description
              sales_size
              sales_uom_description
              availability
              retail_price
              primary_image
              __typename
            }
            total_count
            __typename
          }
        }
        """

        payload = {
            "operationName": "SearchProducts",
            "variables": {
                "storeCode": store_code,
                "availability": "1",
                "published": "1",
                "search": search_term,
                "currentPage": 1,
                "pageSize": 50
            },
            "query": query
        }

        try:
            response = self._make_request_with_retry('post', self.BASE_URL, json=payload)
            return response.json()
        except requests.RequestException as e:
            print(f"Error searching for '{search_term}': {e}")
            return None

    def get_products_by_skus(self, store_code: str, skus: List[str]) -> Optional[Dict]:
        """Get specific products by their SKU codes."""
        query = """
        query SearchProducts($arr: [String], $storeCode: String = "226") {
          products(filter: {sku: {in: $arr}, store_code: {eq: $storeCode}}, pageSize: 125) {
            items {
              sku
              published
              availability
              item_title
              sales_size
              sales_uom_description
              retail_price
              __typename
            }
            __typename
          }
        }
        """

        payload = {
            "operationName": "SearchProducts",
            "variables": {
                "storeCode": store_code,
                "arr": skus
            },
            "query": query
        }

        try:
            response = self._make_request_with_retry('post', self.BASE_URL, json=payload)
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching SKUs {skus}: {e}")
            return None


class TraderJoesDB:
    """SQLite database handler for storing product information."""

    def __init__(self, db_path: str = "traderjoes.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize the database with required tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                sku TEXT,
                retail_price TEXT,
                item_title TEXT,
                inserted_at TEXT,
                store_code TEXT,
                availability TEXT,
                item_description TEXT,
                sales_size TEXT,
                sales_uom_description TEXT,
                url_key TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def insert_items(self, items: List[Dict], store_code: str):
        """Insert items into the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        current_time = datetime.now().isoformat()

        for item in items:
            cursor.execute('''
                INSERT INTO items
                (sku, retail_price, item_title, inserted_at, store_code, availability,
                 item_description, sales_size, sales_uom_description, url_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.get('sku', ''),
                item.get('retail_price', ''),
                item.get('item_title', ''),
                current_time,
                store_code,
                item.get('availability', ''),
                item.get('item_description', ''),
                item.get('sales_size', ''),
                item.get('sales_uom_description', ''),
                item.get('url_key', '')
            ))

        conn.commit()
        changes = conn.total_changes
        conn.close()
        return changes


def fetch_store_data(api: TraderJoesAPI, db: TraderJoesDB, store_code: str):
    """Fetch all data for a specific store."""
    print(f"Fetching data for store {store_code}...")

    # Get first page to determine total pages
    first_page = api.fetch_products_by_store(store_code, 1)
    if not first_page or 'data' not in first_page:
        print(f"Failed to fetch data for store {store_code}")
        return 0

    products_data = first_page['data']['products']
    total_pages = products_data['page_info']['total_pages']
    total_items = 0

    # Process first page
    items = products_data['items']
    if items:
        changes = db.insert_items(items, store_code)
        total_items += len(items)
        print(f"Store {store_code}: Page 1/{total_pages} - {len(items)} items")

    # Fetch remaining pages if any
    if total_pages > 1:
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for page in range(2, min(total_pages + 1, 26)):  # Limit to 25 pages like original
                future = executor.submit(api.fetch_products_by_store, store_code, page)
                futures.append((future, page))

            for future, page_num in futures:
                try:
                    result = future.result(timeout=30)
                    if result and 'data' in result:
                        items = result['data']['products']['items']
                        if items:
                            db.insert_items(items, store_code)
                            total_items += len(items)
                            print(f"Store {store_code}: Page {page_num}/{total_pages} - {len(items)} items")
                except Exception as e:
                    print(f"Error processing page {page_num} for store {store_code}: {e}")

    return total_items


def main():
    parser = argparse.ArgumentParser(description="Trader Joe's Price Tracking")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Fetch command
    fetch_parser = subparsers.add_parser('fetch', help='Fetch price data from stores')
    fetch_parser.add_argument('--stores', nargs='*', default=['701', '31', '546', '452'],
                             help='Store codes to fetch (default: Chicago, LA, NYC, Austin)')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search for products')
    search_parser.add_argument('term', help='Search term')
    search_parser.add_argument('--store', default='226', help='Store code (default: 226)')

    # Lookup command
    lookup_parser = subparsers.add_parser('lookup', help='Look up products by SKU')
    lookup_parser.add_argument('skus', nargs='+', help='SKU codes to look up')
    lookup_parser.add_argument('--store', default='226', help='Store code (default: 226)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    api = TraderJoesAPI()
    db = TraderJoesDB()

    if args.command == 'fetch':
        print(f"Fetching from stores: {args.stores}")
        start_time = time.time()

        total_items = 0
        for store in args.stores:
            store_items = fetch_store_data(api, db, store)
            total_items += store_items

        elapsed = time.time() - start_time
        print(f"\nCompleted! Fetched {total_items} items in {elapsed:.1f} seconds")

    elif args.command == 'search':
        result = api.search_products(args.store, args.term)
        if result and 'data' in result:
            items = result['data']['products']['items']
            print(f"\nFound {len(items)} results for '{args.term}':")
            for item in items[:10]:  # Show first 10 results
                print(f"  {item['sku']}: {item['item_title']} - ${item['retail_price']}")
        else:
            print(f"No results found for '{args.term}'")

    elif args.command == 'lookup':
        result = api.get_products_by_skus(args.store, args.skus)
        if result and 'data' in result:
            items = result['data']['products']['items']
            print(f"\nFound {len(items)} products:")
            for item in items:
                print(f"  {item['sku']}: {item['item_title']} - ${item['retail_price']}")
        else:
            print("No products found for the given SKUs")


if __name__ == "__main__":
    main()
