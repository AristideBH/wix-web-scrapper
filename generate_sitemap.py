import asyncio
import time
from urllib.parse import urljoin
import logging

from playwright.async_api import async_playwright, Error as PlaywrightError, TimeoutError


async def get_url_from_clickable_element(page, selector, max_retries=1):
    for attempt in range(1, max_retries + 1):
        print(f"Attempt {attempt}: Clicking element and retrieving URL...")
        try:
            await page.click(selector)
            await page.wait_for_load_state('networkidle')
            url = page.url
            print(f"Success! Retrieved URL: {url}")
            return url
        except Exception as e:
            print(f"Error on attempt {attempt}: {e}. Retrying...")
    raise Exception(f"Failed to get URL after {max_retries} attempts")


async def crawl_wix_site(page, base_url, max_pages=100):
    visited_urls = set()
    urls_to_visit = [base_url]
    
    # Add logging for debugging
    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    
    logger.debug(f"Starting crawl with base URL: {base_url}")
    logger.debug(f"Initial URLs to visit: {urls_to_visit}")
    while urls_to_visit and len(visited_urls) < max_pages:
        current_url = urls_to_visit.pop(0)
        if current_url in visited_urls:
            continue

        await page.goto(current_url)

        await page.evaluate('''
            window.getXPath = function(el) {
                if (!el || typeof el !== 'object') return '';
                if (el.id && el.id !== '') return 'id("' + el.id + '")';
                if (el === document.body) return el.tagName;

                var ix = 0;
                var siblings = el.parentNode ? el.parentNode.childNodes : [];
                for (var i = 0; i < siblings.length; i++) {
                    var sibling = siblings[i];
                    if (sibling === el)
                        return getXPath(el.parentNode) + '/' + el.tagName + '[' + (ix + 1) + ']';
                    if (sibling.nodeType === 1 && sibling.tagName === el.tagName)
                        ix++;
                }
                return '';
            };
        ''')

        visited_urls.add(current_url)

        # Regular link crawling
        for link in await page.query_selector_all('a[href]'):
            href = await link.get_attribute('href')
            full_url = urljoin(current_url, href)
            if full_url not in visited_urls and full_url.startswith(base_url):
                urls_to_visit.append(full_url)

        # Crawling elements with role="link"
        link_elements = await page.query_selector_all('[role="link"]')
        for element in link_elements:
            selector = f'[role="link"][id="{await element.get_attribute("id")}"]'
            url = await get_url_from_clickable_element(page, selector)
            if url and url != current_url and url not in visited_urls and url.startswith(base_url):
                urls_to_visit.append(url)

    return list(visited_urls)

async def generate_sitemap(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        base_url = url
        visited_urls = await crawl_wix_site(page, base_url)
        
        await browser.close()
    
    return visited_urls

if __name__ == "__main__":
    wix_url = "https://ogenuite.wixsite.com/goo-studio"
    sitemap = asyncio.run(generate_sitemap(wix_url))
    for url in sitemap:
        print(url)
