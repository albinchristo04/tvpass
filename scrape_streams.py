#!/usr/bin/env python3
"""
IPTV M3U to M3U8 Stream Scraper
Extracts real streaming URLs from M3U playlists and saves to JSON
"""

import requests
import json
import re
import time
from datetime import datetime
from urllib.parse import urlparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import urllib3

# Suppress SSL warnings globally
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StreamScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        })
        self.timeout = 15
        
    def parse_m3u(self, content):
        """Parse M3U content and extract channel information"""
        lines = content.strip().split('\n')
        channels = []
        current_channel = None
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('#EXTINF:'):
                match = re.match(r'#EXTINF:(-?\d+)(?:\s+(.*))?,(.*)', line)
                if match:
                    current_channel = {
                        'duration': int(match.group(1)) if match.group(1) else -1,
                        'attributes': match.group(2) if match.group(2) else '',
                        'name': match.group(3).strip() if match.group(3) else 'Unknown Channel',
                        'original_url': '',
                        'stream_url': '',
                        'logo': '',
                        'group': 'Uncategorized',
                        'status': 'unknown',
                        'last_checked': None
                    }
                    
                    logo_match = re.search(r'tvg-logo="([^"]*)"', line)
                    if logo_match:
                        current_channel['logo'] = logo_match.group(1)
                    
                    group_match = re.search(r'group-title="([^"]*)"', line)
                    if group_match:
                        current_channel['group'] = group_match.group(1)
                        
            elif line and not line.startswith('#') and current_channel is not None:
                current_channel['original_url'] = line
                channels.append(current_channel)
                current_channel = None
                
        logger.info(f"Parsed {len(channels)} channels from M3U")
        return channels
    
    def get_real_stream_url(self, url, max_redirects=5):
        """Follow redirects to get the actual M3U8 stream URL"""
        try:
            headers = self.session.headers.copy()
            parsed_url = urlparse(url)
            
            if 'tvpass.org' in parsed_url.netloc or 'thetvapp.to' in parsed_url.netloc:
                headers.update({
                    'Referer': f"{parsed_url.scheme}://{parsed_url.netloc}/",
                    'Origin': f"{parsed_url.scheme}://{parsed_url.netloc}"
                })
            
            response = self.session.head(
                url, 
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
                verify=False
            )
            
            final_url = response.url
            
            if any(ext in final_url.lower() for ext in ['.m3u8', '.ts', '/hls/', '/live/']):
                stream_response = self.session.get(
                    final_url,
                    headers=headers,
                    timeout=self.timeout,
                    stream=True,
                    verify=False
                )  # ✅ closed properly here
                
                if stream_response.status_code == 200:
                    content_type = stream_response.headers.get('content-type', '').lower()
                    if 'mpegurl' in content_type or 'm3u8' in content_type:
                        return final_url, 'working'
                    elif stream_response.headers.get('content-length'):
                        return final_url, 'working'
                    else:
                        try:
                            chunk = next(stream_response.iter_content(chunk_size=1024))
                            if b'#EXTM3U' in chunk or b'#EXT-X-' in chunk:
                                return final_url, 'working'
                        except:
                            pass
                        return final_url, 'unknown'
                else:
                    return final_url, f'error_{stream_response.status_code}'
            else:
                return final_url, 'invalid_format'
                
        except requests.exceptions.Timeout:
            return url, 'timeout'
        except requests.exceptions.ConnectionError:
            return url, 'connection_error'
        except Exception as e:
            logger.warning(f"Error checking stream {url}: {str(e)}")
            return url, f'error_{str(e)[:50]}'
    
    def check_channel_batch(self, channels_batch):
        results = []
        for channel in channels_batch:
            logger.info(f"Checking: {channel['name']}")
            
            stream_url, status = self.get_real_stream_url(channel['original_url'])
            
            channel.update({
                'stream_url': stream_url,
                'status': status,
                'last_checked': datetime.utcnow().isoformat() + 'Z'
            })
            
            results.append(channel)
            time.sleep(0.5)
            
        return results
    
    def scrape_streams(self, m3u_url, max_workers=5):
        logger.info(f"Starting scrape of {m3u_url}")
        
        try:
            response = self.session.get(m3u_url, timeout=30)
            response.raise_for_status()
            channels = self.parse_m3u(response.text)
            
            if not channels:
                logger.error("No channels found in M3U")
                return []
            
            batch_size = max(1, len(channels) // max_workers)
            channel_batches = [channels[i:i + batch_size] for i in range(0, len(channels), batch_size)]
            logger.info(f"Processing {len(channels)} channels in {len(channel_batches)} batches")
            
            all_results = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_batch = {executor.submit(self.check_channel_batch, batch): batch for batch in channel_batches}
                for future in as_completed(future_to_batch):
                    try:
                        batch_results = future.result()
                        all_results.extend(batch_results)
                        logger.info(f"Completed batch: {len(batch_results)} channels")
                    except Exception as e:
                        logger.error(f"Batch processing error: {str(e)}")
            
            all_results.sort(key=lambda x: (x['status'] != 'working', x['group'], x['name']))
            logger.info(f"Scraping completed: {len(all_results)} channels processed")
            working_count = sum(1 for ch in all_results if ch['status'] == 'working')
            logger.info(f"Working streams: {working_count}/{len(all_results)}")
            
            return all_results
            
        except Exception as e:
            logger.error(f"Scraping failed: {str(e)}")
            return []
    
    def save_to_json(self, channels, output_file='streams.json'):
        output_data = {
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'total_channels': len(channels),
            'working_channels': sum(1 for ch in channels if ch['status'] == 'working'),
            'channels': channels
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(channels)} channels to {output_file}")

def main():
    M3U_URL = 'https://raw.githubusercontent.com/abusaeeidx/IPTV-Scraper-Zilla/refs/heads/main/TVPass.m3u'
    OUTPUT_FILE = os.environ.get('OUTPUT_FILE', 'streams.json')
    MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '3'))
    
    logger.info("Starting IPTV stream scraper")
    logger.info(f"M3U URL: {M3U_URL}")
    logger.info(f"Output file: {OUTPUT_FILE}")
    logger.info(f"Max workers: {MAX_WORKERS}")
    
    scraper = StreamScraper()
    channels = scraper.scrape_streams(M3U_URL, max_workers=MAX_WORKERS)
    
    if channels:
        scraper.save_to_json(channels, OUTPUT_FILE)
        logger.info("Scraping completed successfully")
        total = len(channels)
        working = sum(1 for ch in channels if ch['status'] == 'working')
        print(f"\nSUMMARY:")
        print(f"Total channels: {total}")
        print(f"Working streams: {working}")
        print(f"Success rate: {(working/total*100):.1f}%")
    else:
        logger.error("No channels were processed")
        exit(1)

if __name__ == "__main__":
    main()
