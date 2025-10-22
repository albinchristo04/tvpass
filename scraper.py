import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
import time
import sys

# Try to import selenium, fall back to requests if not available
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Warning: Selenium not available, will use basic HTTP requests")

class StreamScraper:
    def __init__(self, base_url="https://streamtpmedia.com"):
        self.base_url = base_url
        self.events_url = f"{base_url}/eventos.html"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': base_url,
        }
    
    def setup_driver(self):
        """Setup Chrome driver for Selenium"""
        if not SELENIUM_AVAILABLE:
            return None
        
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument(f'user-agent={self.headers["User-Agent"]}')
            
            # Try to find Chrome binary in common locations
            import shutil
            chrome_paths = [
                '/usr/bin/google-chrome',
                '/usr/bin/google-chrome-stable',
                '/usr/bin/chromium-browser',
                '/usr/bin/chromium',
            ]
            
            chrome_binary = None
            for path in chrome_paths:
                if shutil.which(path.split('/')[-1]):
                    chrome_binary = shutil.which(path.split('/')[-1])
                    break
            
            if chrome_binary:
                chrome_options.binary_location = chrome_binary
                print(f"Using Chrome binary: {chrome_binary}")
            
            driver = webdriver.Chrome(options=chrome_options)
            return driver
        except Exception as e:
            print(f"Error setting up Chrome driver: {e}")
            return None
    
    def fetch_page_selenium(self, url):
        """Fetch page content using Selenium"""
        driver = self.setup_driver()
        if not driver:
            return None
        
        try:
            print(f"Loading page with Selenium: {url}")
            driver.get(url)
            
            # Wait for content to load (adjust selector based on actual page)
            time.sleep(5)  # Give time for JavaScript to execute
            
            html_content = driver.page_source
            driver.quit()
            return html_content
        except Exception as e:
            print(f"Error fetching with Selenium: {e}")
            if driver:
                driver.quit()
            return None
    
    def fetch_page(self, url):
        """Fetch page content"""
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def extract_m3u8_from_iframe(self, iframe_url):
        """Extract m3u8 URL from iframe content"""
        try:
            print(f"  Checking iframe: {iframe_url}")
            content = self.fetch_page(iframe_url)
            if not content:
                return None
            
            # Look for m3u8 URLs with various patterns
            m3u8_patterns = [
                r'["\']([^"\']*\.m3u8[^"\']*)["\']',
                r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'src:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'(https?://[^\s"\'>]+\.m3u8[^\s"\'>]*)',
            ]
            
            for pattern in m3u8_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if match.startswith('http'):
                        print(f"  ✓ Found m3u8: {match}")
                        return match
            
            print(f"  ✗ No m3u8 found in iframe")
            return None
        except Exception as e:
            print(f"  Error extracting m3u8: {e}")
            return None
    
    def extract_events(self):
        """Extract all events from the eventos.html page"""
        print(f"Fetching page: {self.events_url}")
        
        # Try Selenium first if available
        if SELENIUM_AVAILABLE:
            html_content = self.fetch_page_selenium(self.events_url)
        else:
            html_content = self.fetch_page(self.events_url)
        
        if not html_content:
            print("Failed to fetch page content")
            return []
        
        # Save HTML for debugging
        with open('debug_page.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        print("Saved page HTML to debug_page.html")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        events = []
        
        # Method 1: Look for input/textarea elements with iframe URLs
        print("\n=== Method 1: Input/Textarea elements ===")
        input_elements = soup.find_all(['input', 'textarea'])
        print(f"Found {len(input_elements)} input/textarea elements")
        
        iframe_urls = []
        for elem in input_elements:
            value = elem.get('value', '') or elem.get_text(strip=True)
            if value and ('global' in value or 'streamtp' in value):
                print(f"  Found URL: {value}")
                iframe_urls.append(value)
        
        # Method 2: Search raw HTML for iframe URL patterns
        print("\n=== Method 2: Regex patterns ===")
        patterns = [
            r'(https?://[^\s<>"\']+/global\d+\.php\?[^\s<>"\']+)',
            r'(https?://streamtp\d+\.com/[^\s<>"\']+)',
            r'value=["\']([^"\']*global\d+\.php[^"\']*)["\']',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                if match not in iframe_urls:
                    print(f"  Found URL: {match}")
                    iframe_urls.append(match)
        
        # Method 3: Look for event title patterns
        print("\n=== Method 3: Event titles ===")
        event_pattern = r'(\d{2}:\d{2})\s*-\s*([^<>\n]{10,100})'
        event_matches = re.findall(event_pattern, html_content)
        print(f"Found {len(event_matches)} event titles")
        
        for time_str, match_str in event_matches[:5]:  # Show first 5
            print(f"  {time_str} - {match_str[:50]}...")
        
        # Combine events with iframes
        print(f"\n=== Processing {len(iframe_urls)} events ===")
        for idx, iframe_url in enumerate(iframe_urls):
            try:
                # Make sure URL is absolute
                if not iframe_url.startswith('http'):
                    iframe_url = urljoin(self.base_url, iframe_url)
                
                # Get event title if available
                title = f"Event {idx + 1}"
                if idx < len(event_matches):
                    time_str, match_str = event_matches[idx]
                    title = f"{time_str} - {match_str.strip()}"
                
                event_data = {
                    'id': f"event_{idx + 1}",
                    'title': title,
                    'iframe_url': iframe_url,
                    'm3u8_url': '',
                    'timestamp': datetime.utcnow().isoformat(),
                    'referer': self.events_url,
                    'headers': {
                        'User-Agent': self.headers['User-Agent'],
                        'Referer': self.events_url,
                        'Origin': self.base_url,
                    }
                }
                
                print(f"\n[{idx + 1}/{len(iframe_urls)}] {title}")
                
                # Extract m3u8 from iframe
                m3u8_url = self.extract_m3u8_from_iframe(iframe_url)
                if m3u8_url:
                    event_data['m3u8_url'] = m3u8_url
                    event_data['headers']['Referer'] = iframe_url
                    parsed = urlparse(iframe_url)
                    event_data['headers']['Origin'] = f"{parsed.scheme}://{parsed.netloc}"
                
                events.append(event_data)
                time.sleep(0.5)
            
            except Exception as e:
                print(f"Error processing event: {e}")
                continue
        
        return events
    
    def save_to_json(self, events, filename='events.json'):
        """Save events to JSON file"""
        output = {
            'last_updated': datetime.utcnow().isoformat(),
            'total_events': len(events),
            'events': events
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*50}")
        print(f"✓ Saved {len(events)} events to {filename}")
        print(f"{'='*50}")
        return filename

def main():
    print("="*50)
    print("Stream Event Scraper")
    print("="*50)
    
    scraper = StreamScraper()
    events = scraper.extract_events()
    
    if events:
        print(f"\n✓ Successfully extracted {len(events)} events")
        scraper.save_to_json(events)
    else:
        print("\n✗ No events found")
        scraper.save_to_json([])

if __name__ == "__main__":
    main()
