import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
import time

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
            
            # Look for m3u8 URLs in the content with various patterns
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
                        print(f"  Found m3u8: {match}")
                        return match
            
            return None
        except Exception as e:
            print(f"  Error extracting m3u8 from {iframe_url}: {e}")
            return None
    
    def extract_events(self):
        """Extract all events from the eventos.html page"""
        print(f"Fetching page: {self.events_url}")
        html_content = self.fetch_page(self.events_url)
        if not html_content:
            print("Failed to fetch page content")
            return []
        
        soup = BeautifulSoup(html_content, 'html.parser')
        events = []
        
        # Method 1: Look for input/textarea elements containing iframe URLs
        input_elements = soup.find_all(['input', 'textarea'])
        iframe_urls = []
        
        for elem in input_elements:
            value = elem.get('value', '') or elem.get_text(strip=True)
            if 'global' in value and '.php' in value:
                iframe_urls.append(value)
        
        print(f"Found {len(iframe_urls)} iframe URLs in input/textarea elements")
        
        # Method 2: Look for any text containing iframe URLs
        if not iframe_urls:
            # Search for patterns like global1.php?stream=
            pattern = r'(https?://[^\s<>"]+/global\d+\.php\?stream=[^\s<>"]+)'
            iframe_urls = re.findall(pattern, html_content)
            print(f"Found {len(iframe_urls)} iframe URLs via regex")
        
        # Method 3: Look for event titles/descriptions
        # Common patterns: time + match description
        event_pattern = r'(\d{2}:\d{2})\s*-\s*([^<>\n]+)'
        event_matches = re.findall(event_pattern, html_content)
        
        print(f"Found {len(event_matches)} event titles")
        
        # Combine events with iframes
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
                
                print(f"\nProcessing: {title}")
                
                # Extract m3u8 from iframe
                m3u8_url = self.extract_m3u8_from_iframe(iframe_url)
                if m3u8_url:
                    event_data['m3u8_url'] = m3u8_url
                    # Update headers for m3u8 playback
                    event_data['headers']['Referer'] = iframe_url
                    parsed = urlparse(iframe_url)
                    event_data['headers']['Origin'] = f"{parsed.scheme}://{parsed.netloc}"
                else:
                    print(f"  No m3u8 found")
                
                events.append(event_data)
                
                # Small delay to avoid overwhelming the server
                time.sleep(0.5)
            
            except Exception as e:
                print(f"Error processing iframe {iframe_url}: {e}")
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
        
        print(f"\nSaved {len(events)} events to {filename}")
        return filename

def main():
    scraper = StreamScraper()
    
    print("Starting event scraper...")
    events = scraper.extract_events()
    
    if events:
        print(f"\n✓ Successfully extracted {len(events)} events")
        scraper.save_to_json(events)
    else:
        print("\n✗ No events found")
        # Create empty file to maintain consistency
        scraper.save_to_json([])

if __name__ == "__main__":
    main()
