import asyncio
from urllib.parse import urljoin
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

async def get_url_from_clickable_element(page, selector, max_retries=3):
    current_url = page.url
    for attempt in range(1, max_retries + 1):
        try:
            spinner_thread = threading.Thread(target=spinner_with_url, args=(current_url,))
            spinner_thread.start()
            
            await page.click(selector)
            await page.wait_for_load_state('networkidle')
            new_url = page.url
            
            spinner_thread.do_run = False
            spinner_thread.join()
            sys.stdout.write('\r' + ' ' * (len(current_url) + 20) + '\r')
            sys.stdout.flush()
            
            if new_url != current_url:
                print(f"  {Fore.GREEN}Success! Retrieved new URL: {new_url}{Style.RESET_ALL}")
                return new_url
            else:
                print(f"  {Fore.YELLOW}Clicked element did not change URL{Style.RESET_ALL}")
                return None
        except Exception as e:
            print(f"  {Fore.RED}Error on attempt {attempt}: {e}. Retrying...{Style.RESET_ALL}")
    raise Exception(f"Failed to get URL after {max_retries} attempts")


async def crawl_wix_site(page, base_url):
    visited_urls = set()
    to_visit = [base_url]

    while to_visit:
        current_url = to_visit.pop(0)
        if current_url in visited_urls:
            continue

        print(f"\n{Fore.CYAN}Visiting: {current_url}{Style.RESET_ALL}")
        await page.goto(current_url)
        visited_urls.add(current_url)

        print(f"  {Fore.YELLOW}Searching for a[href] elements...{Style.RESET_ALL}")
        href_links = await page.query_selector_all('a[href]')
        print(f"  {Fore.GREEN}Found {len(href_links)} a[href] elements{Style.RESET_ALL}")
        for link in href_links:
            href = await link.get_attribute('href')
            if href:
                full_url = urljoin(base_url, href)
                if full_url not in visited_urls and full_url not in to_visit and full_url.startswith(base_url):
                    to_visit.append(full_url)
                    print(f"    {Fore.MAGENTA}Found new URL from href: {full_url}{Style.RESET_ALL}")

        print(f"  {Fore.YELLOW}Searching for role='link' elements...{Style.RESET_ALL}")
        link_elements = await page.query_selector_all('[role="link"]')
        print(f"  {Fore.GREEN}Found {len(link_elements)} role='link' elements{Style.RESET_ALL}")
        for element in link_elements:
            try:
                url = await get_url_from_clickable_element(page, '[role="link"]')
                if url and url not in visited_urls and url not in to_visit and url.startswith(base_url):
                    to_visit.append(url)
                    print(f"    {Fore.MAGENTA}Found new URL from role=link: {url}{Style.RESET_ALL}")
                await page.goto(current_url)
            except Exception as e:
                print(f"    {Fore.RED}Error processing role=link element: {e}{Style.RESET_ALL}")

        print(f"{Fore.BLUE}Finished processing {current_url}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}URLs to visit: {len(to_visit)}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Visited URLs: {len(visited_urls)}{Style.RESET_ALL}")

    return visited_urls

async def generate_sitemap(wix_url):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        sitemap = await crawl_wix_site(page, wix_url)
        await browser.close()
    return sitemap

if __name__ == "__main__":
    wix_url = "https://ogenuite.wixsite.com/goo-studio"
    sitemap = asyncio.run(generate_sitemap(wix_url))
    print(f"\n{Fore.GREEN}Sitemap:{Style.RESET_ALL}")
    for url in sitemap:
        print(url)
