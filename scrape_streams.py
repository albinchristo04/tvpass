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

# 🔕 Suppress SSL warnings globally
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
