import asyncio

from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

from colorama import init, Fore, Style

import threading
import itertools

import sys
import time


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


def spinner():

    spinner = itertools.cycle(["-", "/", "|", "\\"])

    while getattr(threading.current_thread(), "do_run", True):

        sys.stdout.write(f"\r{next(spinner)}")

        sys.stdout.flush()

        time.sleep(0.1)


def log(message, color_name="info", indent=0):

    color = LOG_COLORS.get(color_name, Fore.WHITE)

    indent_str = "  " * indent

    print(f"{color}{indent_str}{message[:100]}{Style.RESET_ALL}")


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

        role_link_elements = await page.query_selector_all('[role="link"]')

        for index, element in enumerate(role_link_elements, start=1):

            try:

                url = await get_url_from_clickable_element(
                    page, f'[role="link"]:nth-of-type({index})'
                )

                if url and urlparse(url).netloc == urlparse(base_url).netloc:
                    new_urls.append(url)
                    log(f"New URL: {urlparse(url).path}", "url", indent=2)
                await page.goto(original_url)

            except Exception as e:

                log(f"Error: {str(e)[:50]}...", "error", indent=2)

            await page.wait_for_load_state("networkidle")

    return new_urls


async def crawl_wix_site(page, base_url):

    visited_urls = set()

    to_visit = [base_url]

    print(f"\n{Fore.YELLOW}Processing {urlparse(base_url).path}{Style.RESET_ALL}")

    spinner_thread = threading.Thread(target=spinner)
    spinner_thread.start()

    try:

        while to_visit:

            current_url = to_visit.pop(0)

            if current_url in visited_urls:
                continue

            log(f"Visiting: {urlparse(current_url).path}", "processing")
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


async def generate_sitemap(wix_url):

    async with async_playwright() as p:

        browser = await p.chromium.launch()

        page = await browser.new_page()

        sitemap = await crawl_wix_site(page, wix_url)

        await browser.close()
    return sitemap


if __name__ == "__main__":

    wix_url = "https://ogenuite.wixsite.com/goo-studio/"

    sitemap = asyncio.run(generate_sitemap(wix_url))

    log("\nSitemap:", "success")

    for url in sitemap:

        print(urlparse(url).path)
