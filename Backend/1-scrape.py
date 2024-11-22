import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import pdfplumber
import time
from bs4 import BeautifulSoup
import re
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

def fetch_sitemap(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.content

def parse_sitemap(xml_data):
    root = ET.fromstring(xml_data)
    urls = []
    lastmods = []
    ns = {'sitemaps': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    for url in root.findall(".//sitemaps:url", ns):
        loc = url.find("sitemaps:loc", ns).text
        lastmod = url.find("sitemaps:lastmod", ns).text if url.find("sitemaps:lastmod", ns) is not None else None
        urls.append(loc)
        lastmods.append(lastmod)
    return urls, lastmods

def setup_driver():
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.headless = True  # Run in headless mode
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def fetch_pdf_content(pdf_url):
    pdf_file_path = 'temp.pdf'
    try:
        # Make the request and handle the response
        response = requests.get(pdf_url)
        response.raise_for_status()

        # Write the PDF content to a temporary file
        with open(pdf_file_path, 'wb') as f:
            f.write(response.content)
        
        # Extract text from the downloaded PDF
        text_content = []
        with pdfplumber.open(pdf_file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_content.append(page_text)
        
        # Return the combined text content or a default message if empty
        return ' '.join(text_content) if text_content else 'No text found in PDF'
    except (requests.exceptions.RequestException, Exception) as e:
        print(f"Error fetching or processing PDF from {pdf_url}: {str(e)}")
        return 'Error fetching or processing PDF'
    finally:
        # Clean up the temporary file if it exists
        if os.path.exists(pdf_file_path):
            os.remove(pdf_file_path)

def scrape_page(url, lastmod, driver, existing_urls):
    driver.get(url)
    time.sleep(1)  # Wait for JavaScript to render
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    title = soup.title.string if soup.title else "No title found"
    main_content = soup.find('main')
    if main_content:
        for cookie_div in main_content.find_all("div", id=re.compile("cookie", re.IGNORECASE)):
            cookie_div.decompose()
        texts = ' '.join(main_content.stripped_strings)
    else:
        texts = "Main tag not found or empty"

    pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.IGNORECASE))
    for link in pdf_links:
        pdf_url = link['href']
        if pdf_url.startswith('/'):
            pdf_url = 'https://kommun.falkenberg.se' + pdf_url
        pdf_text = fetch_pdf_content(pdf_url)
        pdf_data = {
            "url": pdf_url,
            "last_modified": lastmod,
            "title": link.text.strip() or "No title",
            "texts": pdf_text,
            "source_url": url
        }
        save_to_json(pdf_data, existing_urls=existing_urls)  # Save each PDF data immediately
    return {
        "url": url,
        "last_modified": lastmod,
        "title": title,
        "texts": texts
    }

def load_existing_urls(filename='scraped_data.json'):
    try:
        with open(filename, 'r') as f:
            existing_data = json.load(f)
        return {item['url']: item for item in existing_data}
    except FileNotFoundError:
        return {}
def save_to_json(data, filename='scraped_data.json', update_mode='update_all', existing_urls=None, update_since=None):
    if existing_urls is None:
        existing_urls = {}

    if update_mode == 'add_missing' and data['url'] in existing_urls:
        return  # Skip saving if URL exists in 'add_missing' mode
    
    if update_mode == 'update_since':
        if data['url'] in existing_urls:
            existing_lastmod = datetime.strptime(existing_urls[data['url']]['last_modified'], '%Y-%m-%dT%H:%M:%SZ')
            if existing_lastmod <= update_since:
                return  # Skip saving if last_modified is not later than update_since date

    existing_urls[data['url']] = data  # Update or add new data

    with open(filename, 'w') as f:
        json.dump(list(existing_urls.values()), f, indent=4)

def main(sitemap_url, update_mode='update_all', update_since=None):
    existing_urls = load_existing_urls()
    driver = setup_driver()
    sitemap = fetch_sitemap(sitemap_url)
    urls, lastmods = parse_sitemap(sitemap)
    for url, lastmod in zip(urls, lastmods):
        if update_mode == 'add_missing' and url in existing_urls:
            continue  # Skip scraping if URL exists and mode is 'add_missing'
        
        if update_mode == 'update_since':
            lastmod_date = datetime.strptime(lastmod, '%Y-%m-%dT%H:%M:%SZ')
            if lastmod_date <= update_since:
                continue  # Skip scraping if last_modified is not later than update_since date
        
        page_data = scrape_page(url, lastmod, driver, existing_urls=existing_urls)
        save_to_json(page_data, update_mode=update_mode, existing_urls=existing_urls, update_since=update_since)
    driver.quit()


# Example sitemap data
sitemap_url = 'https://kommun.falkenberg.se/index.php?option=com_jmap&view=sitemap&format=xml'

# For 'add_missing' mode
# main(sitemap_url, update_mode='add_missing')

# For 'update_all' mode
# main(sitemap_url, update_mode='update_all')

# For 'update_since' mode
update_since_date = datetime(2024, 5, 1)  # Update all pages modified since May 1, 2024
main(sitemap_url, update_mode='update_since', update_since=update_since_date)