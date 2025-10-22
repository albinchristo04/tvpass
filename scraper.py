import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
import os

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
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def extract_m3u8_from_iframe(self, iframe_url):
        """Extract m3u8 URL from iframe content"""
        try:
            # Fetch iframe content
            content = self.fetch_page(iframe_url)
            if not content:
                return None
            
            # Look for m3u8 URLs in the content
            m3u8_patterns = [
                r'(https?://[^\s"\'>]+\.m3u8[^\s"\'>]*)',
                r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'src:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            ]
            
            for pattern in m3u8_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    return matches[0]
            
            return None
        except Exception as e:
            print(f"Error extracting m3u8 from {iframe_url}: {e}")
            return None
    
    def extract_events(self):
        """Extract all events from the eventos.html page"""
        html_content = self.fetch_page(self.events_url)
        if not html_content:
            return []
        
        soup = BeautifulSoup(html_content, 'html.parser')
        events = []
        
        # Find all event containers (adjust selectors based on actual page structure)
        # This is a generic approach - might need adjustment based on actual HTML
        event_elements = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'event|game|match|stream', re.I))
        
        # If no specific event elements found, look for iframes directly
        if not event_elements:
            event_elements = soup.find_all('iframe')
        
        for idx, element in enumerate(event_elements):
            try:
                event_data = {
                    'id': f"event_{idx + 1}",
                    'title': '',
                    'iframe_url': '',
                    'm3u8_url': '',
                    'timestamp': datetime.utcnow().isoformat(),
                    'referer': self.events_url,
                    'headers': {
                        'User-Agent': self.headers['User-Agent'],
                        'Referer': self.events_url,
                        'Origin': self.base_url,
                    }
                }
                
                # Extract title
                title_elem = element.find(['h1', 'h2', 'h3', 'h4', 'span', 'div'], class_=re.compile(r'title|name|event', re.I))
                if title_elem:
                    event_data['title'] = title_elem.get_text(strip=True)
                elif element.get('title'):
                    event_data['title'] = element.get('title')
                
                # Extract iframe URL
                iframe = element.find('iframe') if element.name != 'iframe' else element
                if iframe and iframe.get('src'):
                    iframe_url = urljoin(self.base_url, iframe['src'])
                    event_data['iframe_url'] = iframe_url
                    
                    # Extract m3u8 from iframe
                    m3u8_url = self.extract_m3u8_from_iframe(iframe_url)
                    if m3u8_url:
                        event_data['m3u8_url'] = m3u8_url
                        # Update referer to iframe URL for m3u8 playback
                        event_data['headers']['Referer'] = iframe_url
                        parsed = urlparse(iframe_url)
                        event_data['headers']['Origin'] = f"{parsed.scheme}://{parsed.netloc}"
                
                # Only add events with iframe URLs
                if event_data['iframe_url']:
                    events.append(event_data)
            
            except Exception as e:
                print(f"Error processing event element: {e}")
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
        
        print(f"Saved {len(events)} events to {filename}")
        return filename

def main():
    scraper = StreamScraper()
    
    print("Fetching events...")
    events = scraper.extract_events()
    
    if events:
        print(f"Found {len(events)} events")
        scraper.save_to_json(events)
    else:
        print("No events found")
        # Create empty file to maintain consistency
        scraper.save_to_json([])

if __name__ == "__main__":
    main()
