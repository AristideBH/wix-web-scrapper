import asyncio
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from colorama import init, Fore, Style
import threading
import itertools
import sys
import time


init(autoreset=True)

def spinner_with_url(url):
    spinner = itertools.cycle(['-', '/', '|', '\\'])
    while getattr(threading.current_thread(), "do_run", True):
        sys.stdout.write(f"\r{Fore.YELLOW}Processing {url} {next(spinner)}{Style.RESET_ALL}")
        sys.stdout.flush()
        time.sleep(0.1)

def log(message, color=Fore.WHITE):
    print(f"{color}{message}{Style.RESET_ALL}")

async def get_url_from_clickable_element(page, selector, max_retries=3):
    current_url = page.url
    for attempt in range(1, max_retries + 1):
        try:
            await page.wait_for_selector(selector, state="visible", timeout=10000)
            await page.wait_for_timeout(1000)  # Wait for 1 second
            await page.click(selector)
            await page.wait_for_load_state('networkidle', timeout=15000)
            new_url = page.url

            if new_url != current_url:
                log(f"  Success! Navigated to new URL: {new_url}", Fore.GREEN)
                return new_url
            else:
                log("  Clicked element did not change URL", Fore.YELLOW)
                return None
        except Exception as e:
            log(f"  Error on attempt {attempt}: {e}. Retrying...", Fore.RED)
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    log(f"  Failed to get URL after {max_retries} attempts", Fore.RED)
    return None

async def process_links(page, base_url, selector, link_type):
    log(f"  Searching for {link_type} elements...", Fore.YELLOW)
    elements = await page.query_selector_all(selector)
    log(f"  Found {len(elements)} {link_type} elements", Fore.GREEN)
    new_urls = []

    for element in elements:
        if selector == 'a[href]':
            href = await element.get_attribute('href')
            if href:
                full_url = urljoin(base_url, href)
                new_urls.append(full_url)
                log(f"    Found new URL from href: {full_url}", Fore.MAGENTA)
        else:
            try:
                url = await get_url_from_clickable_element(page, selector)
                if url:
                    new_urls.append(url)
                    log(f"    Found new URL from {link_type}: {url}", Fore.MAGENTA)
                await page.goto(page.url)
            except Exception as e:
                log(f"    Error processing {link_type} element: {e}", Fore.RED)

    return new_urls

async def crawl_wix_site(page, base_url):
    visited_urls = set()
    to_visit = [base_url]

    while to_visit:
        current_url = to_visit.pop(0)
        if current_url in visited_urls:
            continue

        log(f"\nVisiting: {current_url}", Fore.CYAN)
        await page.goto(current_url)
        visited_urls.add(current_url)

        new_urls = await process_links(page, base_url, 'a[href]', 'a[href]')
        new_urls += await process_links(page, base_url, '[role="link"]', 'role=link')

        for url in new_urls:
            if url not in visited_urls and url not in to_visit and url.startswith(base_url):
                to_visit.append(url)

        log(f"Finished processing {current_url}", Fore.BLUE)
        log(f"URLs to visit: {len(to_visit)}", Fore.CYAN)
        log(f"Visited URLs: {len(visited_urls)}", Fore.CYAN)

    return visited_urls

async def generate_sitemap(wix_url):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        sitemap = await crawl_wix_site(page, wix_url)
        await browser.close()
    return sitemap

if __name__ == "__main__":
    wix_url = "https://ogenuite.wixsite.com/goo-studio/copie-de-places"
    sitemap = asyncio.run(generate_sitemap(wix_url))
    log("\nSitemap:", Fore.GREEN)
    for url in sitemap:
        print(url)
