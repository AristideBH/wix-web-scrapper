import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
import time
import json
import os
import aiohttp
import asyncio
import aiofiles
from aiolimiter import AsyncLimiter
import logging

logging.basicConfig(level=logging.DEBUG)
from playwright.async_api import async_playwright

def get_folder_name(url):
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.split('/')
    last_part = path_parts[-1] if path_parts[-1] else path_parts[-2]
    return last_part

def is_valid_url(url, base_domain):
    """Check if the URL is valid and belongs to the same domain."""
    parsed = urlparse(url)
    return bool(parsed.netloc) and parsed.netloc == base_domain

async def get_item_urls(page, base_domain):
    logging.debug("Processing all elements with role='link' attribute")
    
    urls = await page.evaluate(f"""
    async () => {{
        const urls = [];
        const baseDomain = '{base_domain}';
        const baseUrl = window.location.href;
        const linkElements = document.querySelectorAll('[role="link"]');
        
        for (const linkElement of linkElements) {{
            const originalUrl = window.location.href;
            await new Promise(resolve => {{
                linkElement.click();
                setTimeout(resolve, 1000);  // Wait for navigation
            }});
            const newUrl = window.location.href;
            if (new URL(newUrl).hostname === baseDomain && newUrl !== baseUrl && newUrl !== originalUrl) {{
                urls.push(newUrl);
            }}
            await new Promise(resolve => {{
                history.back();
                setTimeout(resolve, 1000);  // Wait for navigation back
            }});
        }}
        
        return urls;
    }}
    """)
    
    if urls:
        logging.debug(f"Found {len(urls)} unique valid URLs from elements with role='link' attribute")
        for url in urls:
            logging.debug(f"URL: {url}")
    else:
        logging.debug("No valid URLs found from elements with role='link' attribute")
    
    return urls





async def get_all_pages(base_url, max_depth=4, max_retries=3):
    base_domain = urlparse(base_url).netloc
    to_crawl = [(base_url, 0)]
    crawled = set()
    limiter = AsyncLimiter(10, 1)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        async with aiohttp.ClientSession() as session:
            while to_crawl:
                current_url, depth = to_crawl.pop(0)
                if current_url not in crawled and depth <= max_depth:
                    print(f"Discovering links on: {current_url}")
                    for attempt in range(max_retries):
                        try:
                            async with limiter:
                                await page.goto(current_url, wait_until='networkidle')
                                html = await page.content()
                            soup = BeautifulSoup(html, 'html.parser')
                            crawled.add(current_url)

                            if depth < max_depth:
                                for link in soup.find_all('a', href=True):
                                    full_url = urljoin(base_url, link['href'])
                                    if is_valid_url(full_url, base_domain) and full_url not in crawled:
                                        to_crawl.append((full_url, depth + 1))
                                
                                for div in soup.find_all('div', class_='item-link-wrapper'):
                                    item_urls = await get_item_urls(page, base_domain)
                                    for item_url in item_urls:
                                        if item_url not in crawled:
                                            to_crawl.append((item_url, depth + 1))

                            break  # Success, exit retry loop
                        except Exception as e:
                            print(f"Error crawling {current_url} (attempt {attempt + 1}): {e}")
                            if attempt == max_retries - 1:
                                print(f"Failed to crawl {current_url} after {max_retries} attempts")
                            else:
                                await asyncio.sleep(2)  # Wait before retrying

        await browser.close()

    return list(crawled)


def create_folder_name(base_url):
    domain = urlparse(base_url).netloc
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"scrapped_data/{domain}_{timestamp}"

async def save_image(url, base_folder, session, page_url):
    """Download and save an image."""
    async with session.get(url) as response:
        if response.status == 200:
            page_folder = get_folder_name(page_url)
            folder = os.path.join(base_folder, page_folder)
            os.makedirs(folder, exist_ok=True)
            filename = os.path.join(folder, url.split('/')[-1])
            async with aiofiles.open(filename, 'wb') as f:
                await f.write(await response.read())
            return filename
    return None

async def scrape_wix_page(url, image_folder, session):
    """Scrape content from a single Wix page."""
    async with session.get(url) as response:
        html = await response.text()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract title
    title = soup.find('title').text if soup.find('title') else "No title found"
    
    # Extract content (adjust selectors as needed)
    content = soup.find('div', class_='PAGES_CONTAINER')
    content_text = content.text if content else "No content found"
    
    # Extract and save image URLs
    images = [img['src'] for img in soup.find_all('img') if 'src' in img.attrs]
    saved_images = []
    for img_url in images:
        saved_path = await save_image(img_url, image_folder, session, url)
        if saved_path:
            saved_images.append(saved_path)
    
    return {
        'url': url,
        'title': title,
        'content': content_text,
        'images': saved_images
    }

async def save_to_json(data, filename):
    """Save scraped data to a JSON file asynchronously."""
    async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=4))

async def main():
    base_url = 'https://ogenuite.wixsite.com/goo-studio/'
    all_pages = await get_all_pages(base_url)

    folder_name = create_folder_name(base_url)
    os.makedirs(folder_name, exist_ok=True)

    image_folder = os.path.join(folder_name, 'images')
    os.makedirs(image_folder, exist_ok=True)

    scraped_data = []

    async with aiohttp.ClientSession() as session:
        for page_url in all_pages:
            print("-" * 50)
            print(f"Scraping: {page_url}")
            page_data = await scrape_wix_page(page_url, image_folder, session)
            scraped_data.append(page_data)
            print(f"Title: {page_data['title']}")
            print(f"Content preview: {page_data['content'][:100]}...")
            print(f"Number of images saved: {len(page_data['images'])}")
            print("-" * 50)

    json_file = os.path.join(folder_name, 'scraped_wix_data.json')
    await save_to_json(scraped_data, json_file)
    print(f"Scraping completed. Data saved to {json_file}")

if __name__ == "__main__":
    asyncio.run(main())
