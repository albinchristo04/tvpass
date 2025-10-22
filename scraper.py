import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
import time
import sys
import base64

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
            chrome_options.page_load_strategy = 'eager'
            
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
            driver.set_page_load_timeout(30)
            return driver
        except Exception as e:
            print(f"Error setting up Chrome driver: {e}")
            return None
    
    def decode_obfuscated_url(self, content):
        """Decode the obfuscated JavaScript to extract m3u8 URL"""
        try:
            # Look for the CD array pattern
            cd_match = re.search(r'CD=\[(.*?)\];', content, re.DOTALL)
            if not cd_match:
                return None
            
            cd_data_str = cd_match.group(1)
            
            # Extract all [index, base64] pairs
            pairs = re.findall(r'\[(\d+),"([^"]+)"\]', cd_data_str)
            if not pairs:
                return None
            
            # Sort by index
            pairs.sort(key=lambda x: int(x[0]))
            
            # Find the key functions (BgpUh and zqOGS values)
            bgpuh_match = re.search(r'function\s+BgpUh\(\)\{return\s+(\d+);\}', content)
            zqogs_match = re.search(r'function\s+zqOGS\(\)\{return\s+(\d+);\}', content)
            
            if not bgpuh_match or not zqogs_match:
                return None
            
            key = int(bgpuh_match.group(1)) + int(zqogs_match.group(1))
            
            # Decode the URL
            url_chars = []
            for _, encoded in pairs:
                try:
                    decoded = base64.b64decode(encoded).decode('utf-8')
                    # Extract numbers from decoded string
                    numbers = re.findall(r'\d+', decoded)
                    if numbers:
                        char_code = int(numbers[0]) - key
                        url_chars.append(chr(char_code))
                except Exception as e:
                    continue
            
            url = ''.join(url_chars)
            
            # Check if it's a valid URL
            if url.startswith('http') and '.m3u8' in url:
                return url
            
            return None
            
        except Exception as e:
            print(f"  Error decoding obfuscated URL: {e}")
            return None
    
    def extract_m3u8_with_selenium(self, iframe_url):
        """Use Selenium to execute JavaScript and capture the m3u8 URL"""
        driver = self.setup_driver()
        if not driver:
            return None
        
        try:
            print(f"  Loading with Selenium: {iframe_url}")
            driver.get(iframe_url)
            
            # Wait for JavaScript to execute
            time.sleep(5)
            
            # Try to extract the playbackURL variable
            try:
                script = """
                try {
                    return window.playbackURL || '';
                } catch(e) {
                    return '';
                }
                """
                playback_url = driver.execute_script(script)
                if playback_url and '.m3u8' in playback_url:
                    print(f"  ✓ Found m3u8 via Selenium: {playback_url}")
                    driver.quit()
                    return playback_url
            except Exception as e:
                print(f"  Could not extract via JS: {e}")
            
            # Try to intercept network requests (requires additional setup)
            # For now, get page source and try to decode
            page_source = driver.page_source
            driver.quit()
            
            # Try to decode from page source
            return self.decode_obfuscated_url(page_source)
            
        except Exception as e:
            print(f"  Error with Selenium: {e}")
            if driver:
                try:
                    driver.quit()
                except:
                    pass
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
            
            time.sleep(3)
            
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
                try:
                    driver.quit()
                except:
                    pass
            return []
    
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
            
            # First try with regular HTTP request and decode
            content = self.fetch_page(iframe_url)
            if content:
                # Try to decode obfuscated URL
                m3u8_url = self.decode_obfuscated_url(content)
                if m3u8_url:
                    print(f"  ✓ Found m3u8 (decoded): {m3u8_url}")
                    return m3u8_url
                
                # Fallback: Look for direct m3u8 URLs
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
                            print(f"  ✓ Found m3u8 (direct): {match}")
                            return match
            
            # If HTTP didn't work, try Selenium for JavaScript execution
            if SELENIUM_AVAILABLE:
                return self.extract_m3u8_with_selenium(iframe_url)
            
            print(f"  ✗ No m3u8 found in iframe")
            return None
            
        except Exception as e:
            print(f"  Error extracting m3u8: {e}")
            return None
    
    def extract_events(self):
        """Extract all events from the eventos.html page"""
        print(f"Fetching page: {self.events_url}")
        
        selenium_urls = []
        if SELENIUM_AVAILABLE:
            print("\n=== Attempting direct URL extraction with Selenium ===")
            try:
                selenium_urls = self.extract_urls_with_selenium(self.events_url)
                print(f"Selenium found {len(selenium_urls)} URLs")
                for url in selenium_urls[:5]:
                    print(f"  {url[:100]}")
            except Exception as e:
                print(f"Selenium extraction failed: {e}")
        
        html_content = self.fetch_page(self.events_url)
        
        if not html_content:
            print("Failed to fetch page content")
            return []
        
        with open('debug_page.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        print("Saved page HTML to debug_page.html")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        events = []
        iframe_urls = []
        event_titles = []
        
        # Extract URLs from various sources
        print("\n=== Extracting URLs ===")
        input_elements = soup.find_all(['input', 'textarea'])
        for elem in input_elements:
            for attr in ['value', 'data-src', 'data-url', 'data-iframe', 'src', 'href']:
                value = elem.get(attr, '')
                if value and ('global' in value.lower() or 'streamtp' in value.lower() or '.php' in value):
                    if value not in iframe_urls:
                        iframe_urls.append(value)
        
        # Add URLs from Selenium
        if selenium_urls:
            for url in selenium_urls:
                if url and url not in iframe_urls:
                    iframe_urls.append(url)
        
        iframe_urls = list(dict.fromkeys(iframe_urls))
        
        # Extract event titles
        title_patterns = [
            r'(\d{2}:\d{2})\s*[-–—]\s*([^<>\n]{10,150})',
        ]
        
        for pattern in title_patterns:
            matches = re.findall(pattern, html_content, re.DOTALL)
            for match in matches:
                if isinstance(match, tuple):
                    time_str, title = match
                    title = re.sub(r'<[^>]+>', '', title).strip()
                    if title and len(title) > 5:
                        event_titles.append((time_str.strip(), title))
        
        seen = set()
        unique_titles = []
        for t in event_titles:
            if t not in seen:
                seen.add(t)
                unique_titles.append(t)
        event_titles = unique_titles
        
        print(f"\nFound {len(iframe_urls)} URLs and {len(event_titles)} titles")
        
        # Process iframe URLs
        for idx, iframe_url in enumerate(iframe_urls):
            try:
                if not iframe_url.startswith('http'):
                    iframe_url = urljoin(self.base_url, iframe_url)
                
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
        
        events_with_streams = sum(1 for e in events if e.get('m3u8_url'))
        events_with_iframes = sum(1 for e in events if e.get('iframe_url'))
        print(f"  Events with iframe URLs: {events_with_iframes}")
        print(f"  Events with m3u8 streams: {events_with_streams}")
        print(f"{'='*50}")
        
        return filename

def main():
    print("="*50)
    print("Stream Event Scraper v2.2 - Enhanced Decoder")
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
