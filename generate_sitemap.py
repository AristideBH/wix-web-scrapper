import asyncio


from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

from colorama import init, Fore, Style

import threading
import itertools

import sys
import time
import os


import json
from collections import defaultdict

import aiohttp


LOG_COLORS = {
    "info": Fore.WHITE,
    "success": Fore.GREEN,
    "warning": Fore.YELLOW,
    "error": Fore.RED,
    "processing": Fore.CYAN,
    "url": Fore.MAGENTA,
    "highlight": Fore.BLUE,
}


init(autoreset=True)


def get_site_name(url):
    parsed_url = urlparse(url)
    return parsed_url.netloc


def ensure_crawled_folder():
    folder_name = "crawled"
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
    return folder_name


def build_structured_sitemap(sitemap):
    structured = defaultdict(dict)

    for url in sitemap:

        path = urlparse(url).path.strip("/").split("/")
        current = structured

        for segment in path:

            if segment not in current:

                current[segment] = {}

            current = current[segment]
    return structured


def spinner():

    spinner_cycle = itertools.cycle(["-", "/", "|", "\\"])

    while getattr(threading.current_thread(), "do_run", True):

        sys.stdout.write(f"\r{next(spinner_cycle)}")

        sys.stdout.flush()

        time.sleep(0.2)


def log(message, color_name="info", indent=0):

    color = LOG_COLORS.get(color_name, Fore.WHITE)

    indent_str = "      " * indent

    print(f"{color}{indent_str}{message[:1000]}{Style.RESET_ALL}")


async def get_url_from_clickable_element(page, selector, max_retries=1):
    original_url = page.url

    indent = 2

    for attempt in range(1, max_retries + 1):

        try:

            await page.wait_for_selector(selector, state="visible", timeout=500)

            await page.wait_for_timeout(1000)

            await page.click(selector)

            await page.wait_for_load_state("networkidle", timeout=15000)

            new_url = page.url

            if new_url != original_url:

                log(f"URL: {urlparse(new_url).path}", "success", indent=indent)

                await page.goto(original_url)

                return new_url

            else:

                log("Click did not change URL", "warning", indent=indent)

                return None

        except Exception as e:

            log(f"Error: {str(e)[:50]}...", "error", indent=indent)

            await asyncio.sleep(2**attempt)

    log(f"Failed after {max_retries} attempts", "error", indent=indent)

    return None


async def process_links(page, base_url, selector):

    log(f"Searching {selector} elements", "warning", indent=1)

    elements = await page.query_selector_all(selector)

    log(f"Found {len(elements)} elements", "success", indent=1)

    new_urls = []

    base_domain = urlparse(base_url).netloc

    if selector == "a[href]":

        for element in elements:

            href = await element.get_attribute("href")

            if href:

                full_url = urljoin(base_url, href)

                if urlparse(full_url).netloc == base_domain:

                    new_urls.append(full_url)

                    log(f"New URL: {urlparse(full_url).path}", "url", indent=2)

    else:  # role=link
        original_url = page.url

        for index, element in enumerate(elements, start=1):

            try:

                url = await get_url_from_clickable_element(
                    page, f'[role="link"]:nth-of-type({index})', max_retries=1
                )

                if url and urlparse(url).netloc == urlparse(base_url).netloc:

                    new_urls.append(url)

                    log(f"New URL: {urlparse(url).path}", "url", indent=2)

                await page.goto(original_url)

            except Exception as e:

                log(f"Error: {str(e)[:50]}...", "error", indent=2)

            await page.wait_for_load_state("networkidle")

    return new_urls


async def crawl_site(page, base_url):

    visited_urls = set()

    to_visit = [base_url]

    print(f"\n{Fore.YELLOW}Processing {(base_url)}{Style.RESET_ALL}")

    spinner_thread = threading.Thread(target=spinner)

    spinner_thread.start()

    async with aiohttp.ClientSession() as session:

        try:

            while to_visit:

                current_url = to_visit.pop(0)

                if current_url in visited_urls:
                    continue

                log(f"Visiting: {urlparse(current_url).path}", "processing")

                # Check content type before navigating

                async with session.head(current_url, allow_redirects=True) as response:

                    content_type = response.headers.get("Content-Type", "").lower()

                    if "text/html" not in content_type:
                        log(
                            f"Skipping non-HTML content: {urlparse(current_url).path}",
                            "warning",
                        )

                        visited_urls.add(current_url)
                        continue

                await page.goto(current_url)

                visited_urls.add(current_url)

                new_urls = await process_links(page, base_url, "a[href]")

                new_urls += await process_links(page, base_url, '[role="link"]')

                for url in new_urls:
                    if (
                        url not in visited_urls
                        and url not in to_visit
                        and url.startswith(base_url)
                    ):

                        to_visit.append(url)

                log(f"Processed: {urlparse(current_url).path}", "highlight")

                log(f"To visit: {len(to_visit)}", "processing", indent=1)

                log(f"Visited: {len(visited_urls)}", "processing", indent=1)

        finally:

            spinner_thread.do_run = False

            spinner_thread.join()

            sys.stdout.write("\r")  # Clear the spinner

            sys.stdout.flush()

    return visited_urls


async def generate_sitemap(site_url):

    async with async_playwright() as p:

        browser = await p.chromium.launch()

        page = await browser.new_page()

        sitemap = await crawl_site(page, site_url)
        await browser.close()

    structured_sitemap = build_structured_sitemap(sitemap)
    return sitemap, structured_sitemap


if __name__ == "__main__":
    site_url = "https://ctrl.xyz/fr"
    sitemap, structured_sitemap = asyncio.run(generate_sitemap(site_url))

    log("\nSitemap:", "success")
    for url in sitemap:
        print(urlparse(url).path)

    # Get the site name and create the filename
    site_name = get_site_name(site_url)
    filename = f"{site_name}-sitemap.json"

    crawled_folder = ensure_crawled_folder()

    # Create the full path for the JSON file
    file_path = os.path.join(crawled_folder, filename)

    # Save structured sitemap to a JSON file with the new filename
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(structured_sitemap, f, ensure_ascii=False, indent=2)

    log(f"\nSitemap saved to '{file_path}'", "success")
