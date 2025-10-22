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
    
    def extract_urls_with_selenium(self, url):
        """Extract URLs directly from DOM using Selenium"""
        driver = self.setup_driver()
        if not driver:
            return []
        
        urls_found = []
        try:
            print(f"Loading page with Selenium for URL extraction: {url}")
            driver.get(url)
            
            # Wait for JavaScript to execute
            time.sleep(10)
            
            # Try to find all input elements and extract their values
            try:
                script = """
                var results = [];
                var inputs = document.querySelectorAll('input, textarea, [data-url], [data-stream]');
                inputs.forEach(function(el) {
                    var value = el.value || el.getAttribute('data-url') || el.getAttribute('data-stream') || el.textContent;
                    if (value && (value.includes('http') || value.includes('global') || value.includes('.php'))) {
                        results.push(value);
                    }
                });
                return results;
                """
                values = driver.execute_script(script)
                print(f"  Found {len(values)} potential URLs via JavaScript")
                urls_found.extend(values)
            except Exception as e:
                print(f"  Error executing JavaScript: {e}")
            
            # Also try to get any iframe src attributes
            try:
                iframes = driver.find_elements(By.TAG_NAME, 'iframe')
                print(f"  Found {len(iframes)} iframe elements")
                for iframe in iframes:
                    src = iframe.get_attribute('src')
                    if src:
                        urls_found.append(src)
            except Exception as e:
                print(f"  Error finding iframes: {e}")
            
            driver.quit()
            return urls_found
            
        except Exception as e:
            print(f"Error in URL extraction: {e}")
            if driver:
                driver.quit()
            return []
        """Fetch page content using Selenium"""
        driver = self.setup_driver()
        if not driver:
            return None
        
        try:
            print(f"Loading page with Selenium: {url}")
            driver.get(url)
            
            # Wait longer for JavaScript to execute and DOM to be built
            print("Waiting for JavaScript to execute...")
            time.sleep(8)
            
            # Try to find any input elements that might contain URLs
            try:
                inputs = driver.find_elements(By.TAG_NAME, 'input')
                print(f"Found {len(inputs)} input elements after JS execution")
            except:
                pass
            
            # Execute JavaScript to try to extract any hidden data
            try:
                # Try to get all input values via JavaScript
                script = """
                var inputs = document.getElementsByTagName('input');
                var values = [];
                for(var i = 0; i < inputs.length; i++) {
                    if(inputs[i].value) values.push(inputs[i].value);
                }
                return values;
                """
                values = driver.execute_script(script)
                print(f"Extracted {len(values)} values via JavaScript")
                for val in values[:3]:
                    print(f"  Sample value: {val[:100]}")
            except Exception as e:
                print(f"Could not execute JavaScript: {e}")
            
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
        
        # First, try to extract URLs directly with Selenium
        if SELENIUM_AVAILABLE:
            print("\n=== Attempting direct URL extraction with Selenium ===")
            selenium_urls = self.extract_urls_with_selenium(self.events_url)
            print(f"Selenium found {len(selenium_urls)} URLs")
            for url in selenium_urls[:5]:
                print(f"  {url[:100]}")
        
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
        
        # NEW: Look for all possible URL containers
        iframe_urls = []
        event_titles = []
        
        print("\n=== Method 1: Input/Textarea elements ===")
        input_elements = soup.find_all(['input', 'textarea'])
        print(f"Found {len(input_elements)} input/textarea elements")
        
        # Check all attributes and text content
        for elem in input_elements:
            # Check all attributes
            for attr in ['value', 'data-src', 'data-url', 'data-iframe', 'src', 'href']:
                value = elem.get(attr, '')
                if value and ('global' in value.lower() or 'streamtp' in value.lower() or '.php' in value):
                    print(f"  Found URL in {attr}: {value}")
                    if value not in iframe_urls:
                        iframe_urls.append(value)
            
            # Check text content
            text = elem.get_text(strip=True)
            if text and ('global' in text.lower() or 'streamtp' in text.lower() or 'http' in text):
                print(f"  Found URL in text: {text}")
                if text not in iframe_urls:
                    iframe_urls.append(text)
        
        # Method 2: Find iframe elements directly
        print("\n=== Method 2: Direct iframe elements ===")
        iframes = soup.find_all('iframe')
        print(f"Found {len(iframes)} iframe elements")
        for iframe in iframes:
            src = iframe.get('src', '') or iframe.get('data-src', '')
            if src:
                print(f"  Found iframe src: {src}")
                if src not in iframe_urls:
                    iframe_urls.append(src)
        
        # Method 3: Search raw HTML with improved regex
        print("\n=== Method 3: Enhanced Regex patterns ===")
        patterns = [
            r'(https?://[^\s<>"\']+/global\d+\.php\?[^\s<>"\']+)',
            r'(https?://streamtp\d+\.com/[^\s<>"\']+)',
            r'value=["\']([^"\']*(?:global|streamtp)[^"\']*)["\']',
            r'src=["\']([^"\']*(?:global|streamtp)[^"\']*)["\']',
            r'data-src=["\']([^"\']*(?:global|streamtp)[^"\']*)["\']',
            r'href=["\']([^"\']*(?:global|streamtp)[^"\']*)["\']',
            # More aggressive pattern for any URL-like string
            r'(https?://[^\s<>"\']+\.php\?[^\s<>"\']+)',
            # Look for URLs in JavaScript strings (may be obfuscated)
            r'["\']+(https?://[^"\']+?global[^"\']+?\.php[^"\']*)["\']',
            r'["\']+(https?://[^"\']+?streamtp[^"\']+?)["\']',
            # Even more aggressive - look for domain patterns
            r'(https://streamtpmedia\.com/[^\s<>"\']+)',
            r'(https://streamtp[0-9]+\.com/[^\s<>"\']+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                if match not in iframe_urls:
                    print(f"  Found URL via regex: {match}")
                    iframe_urls.append(match)
        
        # Method 4: Look for JavaScript variables
        print("\n=== Method 4: JavaScript variables ===")
        js_patterns = [
            r'var\s+\w+\s*=\s*["\']([^"\']*(?:global|streamtp|\.php)[^"\']*)["\']',
            r'const\s+\w+\s*=\s*["\']([^"\']*(?:global|streamtp|\.php)[^"\']*)["\']',
            r'let\s+\w+\s*=\s*["\']([^"\']*(?:global|streamtp|\.php)[^"\']*)["\']',
        ]
        
        for pattern in js_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                if match not in iframe_urls:
                    print(f"  Found URL in JS: {match}")
                    iframe_urls.append(match)
        
        # Method 5: Extract event titles
        print("\n=== Method 5: Event titles ===")
        # Try multiple patterns for event titles
        title_patterns = [
            r'(\d{2}:\d{2})\s*[-–—]\s*([^<>\n]{10,150})',
            r'<[^>]*>(\d{2}:\d{2})[^<]*</[^>]*>[^<]*<[^>]*>([^<]{10,150})',
        ]
        
        for pattern in title_patterns:
            matches = re.findall(pattern, html_content, re.DOTALL)
            for match in matches:
                if isinstance(match, tuple):
                    time_str, title = match
                    title = re.sub(r'<[^>]+>', '', title).strip()
                    if title and len(title) > 5:
                        event_titles.append((time_str.strip(), title))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_titles = []
        for t in event_titles:
            if t not in seen:
                seen.add(t)
                unique_titles.append(t)
        event_titles = unique_titles
        
        print(f"Found {len(event_titles)} unique event titles")
        for time_str, title in event_titles[:5]:
            print(f"  {time_str} - {title[:60]}...")
        
        # Method 6: Look for onclick/data attributes that might contain URLs
        print("\n=== Method 6: Event handlers and data attributes ===")
        onclick_patterns = [
            r'onclick=["\']([^"\']*)["\']',
            r'data-url=["\']([^"\']*)["\']',
            r'data-stream=["\']([^"\']*)["\']',
            r'data-link=["\']([^"\']*)["\']',
        ]
        
        for pattern in onclick_patterns:
            matches = re.findall(pattern, html_content)
            for match in matches:
                if 'http' in match or 'global' in match or 'streamtp' in match:
                    # Extract URL from onclick handler
                    url_match = re.search(r'https?://[^\s\'"]+', match)
                    if url_match:
                        url = url_match.group(0)
                        if url not in iframe_urls:
                            print(f"  Found URL in handler: {url}")
                            iframe_urls.append(url)
        
        # Deduplicate iframe URLs
        iframe_urls = list(dict.fromkeys(iframe_urls))
        
        # Add URLs from Selenium if we got any
        if SELENIUM_AVAILABLE and 'selenium_urls' in locals():
            for url in selenium_urls:
                if url and url not in iframe_urls:
                    iframe_urls.append(url)
            iframe_urls = list(dict.fromkeys(iframe_urls))
        
        print(f"\n=== Processing {len(iframe_urls)} iframe URLs ===")
        print(f"Event titles available: {len(event_titles)}")
        
        # If we have no iframe URLs but have titles, create placeholder events
        if not iframe_urls and event_titles:
            print("\nWARNING: Found titles but no iframe URLs!")
            print("Creating events without stream URLs for reference...")
            
            for idx, (time_str, title) in enumerate(event_titles):
                event_data = {
                    'id': f"event_{idx + 1}",
                    'title': f"{time_str} - {title}",
                    'iframe_url': '',
                    'm3u8_url': '',
                    'timestamp': datetime.utcnow().isoformat(),
                    'referer': self.events_url,
                    'status': 'no_stream_url_found',
                    'headers': {
                        'User-Agent': self.headers['User-Agent'],
                        'Referer': self.events_url,
                        'Origin': self.base_url,
                    }
                }
                events.append(event_data)
        
        # Process iframe URLs
        for idx, iframe_url in enumerate(iframe_urls):
            try:
                # Make sure URL is absolute
                if not iframe_url.startswith('http'):
                    iframe_url = urljoin(self.base_url, iframe_url)
                
                # Get event title if available
                title = f"Event {idx + 1}"
                if idx < len(event_titles):
                    time_str, match_str = event_titles[idx]
                    title = f"{time_str} - {match_str.strip()}"
                
                event_data = {
                    'id': f"event_{idx + 1}",
                    'title': title,
                    'iframe_url': iframe_url,
                    'm3u8_url': '',
                    'timestamp': datetime.utcnow().isoformat(),
                    'referer': self.events_url,
                    'status': 'active',
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
        
        # Print summary
        events_with_streams = sum(1 for e in events if e.get('m3u8_url'))
        events_with_iframes = sum(1 for e in events if e.get('iframe_url'))
        print(f"  Events with iframe URLs: {events_with_iframes}")
        print(f"  Events with m3u8 streams: {events_with_streams}")
        print(f"{'='*50}")
        
        return filename

def main():
    print("="*50)
    print("Stream Event Scraper v2.0")
    print("="*50)
    
    scraper = StreamScraper()
    events = scraper.extract_events()
    
    if events:
        print(f"\n✓ Successfully extracted {len(events)} events")
        scraper.save_to_json(events)
    else:
        print("\n✗ No events found")
        print("Check debug_page.html to investigate page structure")
        scraper.save_to_json([])

if __name__ == "__main__":
    main()
