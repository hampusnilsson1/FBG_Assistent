import os
import time
import uuid
import hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import VectorParams, Distance, PointStruct
import openai
import tiktoken

from bs4 import BeautifulSoup
import re
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import pdfplumber
import xml.etree.ElementTree as ET

import logging

# Constants
QDRANT_URL = "https://qdrant.utvecklingfalkenberg.se"
QDRANT_PORT = 443
EMBEDDING_MODEL = "text-embedding-3-large"  # Using the larger model
BATCH_SIZE = 1000
SLEEP_TIME = 2
VECTOR_SIZE = 3072  # Updated vector size for large embeddings
COLLECTION_NAME = "FalkenbergsKommunsHemsida"

# LOGGING------------------
log_file = "/app/data/update_logg.txt"

log_dir = os.path.dirname(log_file)
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

if not os.path.exists(log_file):
    open(log_file, "w").close()
# Konfigurera logging för att skriva till en fil
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Skapa en handler för att också skriva till konsolen
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console.setFormatter(formatter)
logging.getLogger("").addHandler(console)


### -----------------------
# UUID Gen
def generate_uuid(text):
    hash_object = hashlib.md5(text.encode())
    return str(uuid.UUID(hash_object.hexdigest()))


# Token Count/Calc
def count_tokens(texts, model="text-embedding-3-large"):

    encoding = tiktoken.encoding_for_model(model)
    total_tokens = 0
    for text in texts:
        tokens = encoding.encode(text)
        total_tokens += len(tokens)
    return total_tokens


def calculate_cost_sek(texts, model="text-embedding-3-large"):
    SEK_per_USD = 11
    num_tokens = count_tokens(texts, model)

    # Kostnadsberäkningar per 1000 tokens
    if model == "text-embedding-3-large":
        cost_per_1000_tokens = 0.00013  # USD
    else:
        raise ValueError("Unsupported model")

    # Beräkna kostnaden
    cost = ((num_tokens / 1000) * cost_per_1000_tokens) * SEK_per_USD
    return cost


### Scrappa individuell sida och dess pdfer
def setup_driver():  # Bytar till lokal chromedriver
    chrome_driver_path = "/usr/bin/chromedriver"
    service = Service(chrome_driver_path)
    options = Options()
    options.add_argument("--log-level=3")  # Sätter loggnivån till "FATAL"
    options.add_argument("--no-sandbox")  # Bypass OS security model
    options.add_argument(
        "--disable-dev-shm-usage"
    )  # Overcome limited resource problems
    options.add_argument("--disable-gpu")  # applicable if running on Windows
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("start-maximized")  # Maximize the browser on startup
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def fetch_pdf_content(pdf_url):
    pdf_file_path = "/app/data/temp.pdf"
    try:
        response = requests.get(pdf_url)
        response.raise_for_status()

        with open(pdf_file_path, "wb") as f:
            f.write(response.content)

        text_content = []
        with pdfplumber.open(pdf_file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_content.append(page_text)
        return " ".join(text_content) if text_content else "No text found in PDF"
    except (requests.exceptions.RequestException, Exception) as e:
        logging.info(f"Error fetching or processing PDF from {pdf_url}: {str(e)}")
        return "Error fetching or processing PDF"
    finally:
        if os.path.exists(pdf_file_path):
            os.remove(pdf_file_path)


def fetch_sitemap(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.content


def get_page_details(url, driver, providedTitle=None):
    # Fetch the page content
    if url.lower().endswith(".pdf"):
        pdf_text = fetch_pdf_content(url)
        if providedTitle == None:
            title = url.split("/")[-1]
        else:
            title = providedTitle
        results = []
        results.append({"url": url, "title": title, "texts": pdf_text})
        return results
    else:
        driver.get(url)
        time.sleep(1)  # Wait for JavaScript to render
        soup = BeautifulSoup(driver.page_source, "html.parser")
        title = soup.title.string if soup.title else "No title found"
        main_content = soup.find("main")
        if main_content:
            for cookie_div in main_content.find_all(
                "div", id=re.compile("cookie", re.IGNORECASE)
            ):
                cookie_div.decompose()
            texts = " ".join(main_content.stripped_strings)
        else:
            texts = "Main tag not found or empty"

        results = []

        results.append({"url": url, "title": title, "texts": texts})

        pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.IGNORECASE))
        for link in pdf_links:
            pdf_url = link["href"]
            if "evolution" not in pdf_url:  # Om det inte är en evolution pdf
                if pdf_url.startswith("/"):
                    pdf_url = "https://kommun.falkenberg.se" + pdf_url

                pdf_text = fetch_pdf_content(pdf_url)
                results.append(
                    {
                        "url": pdf_url,
                        "title": link.text.strip() or "No title",
                        "texts": pdf_text,
                        "source_url": url,
                    }
                )
        return results


# Processa en datapunkt
# 1. Process a single data item (site or document)
def process_item_qdrant(item):
    logging.info("Dividing to chunks")
    chunks = get_item_chunks(item)
    logging.info("Dividing to chunks Done")
    logging.info(f"Getting chunks in need of update, url: {item['url']}")
    db_hashes = get_db_chunk_hashes(chunks)
    new_chunks = get_new_chunks(chunks, db_hashes)
    if new_chunks == None or len(new_chunks) == 0:
        logging.info("No Update needed for this item.")
        return 0
    old_urls = get_old_urls(chunks, db_hashes)
    logging.info("Embedding chunks")
    embeddings, chunk_cost_SEK = create_embeddings(new_chunks)
    logging.info(f"Embedding chunks Done")
    logging.info("Removing old chunks")
    remove_old_datapoints(new_chunks, old_urls)
    logging.info("Uploading Embeddings")
    upsert_to_qdrant(new_chunks, embeddings)
    logging.info("Uploading Embeddings Done")
    return chunk_cost_SEK


# 2. Split the item's text into overlapping chunks
def get_item_chunks(item):
    all_chunks = []
    text_chunks = chunk_text(item["texts"], 4000, 300)
    num_chunks = len(text_chunks)
    for index, chunk in enumerate(text_chunks):
        chunk_data = {
            "url": item["url"],
            "title": item["title"],
            "chunk": chunk,
            "chunk_hash": generate_uuid(chunk),
            "chunk_info": f"Chunk {index + 1} of {num_chunks}",
        }
        if "source_url" in item:
            chunk_data["source_url"] = item["source_url"]
        if "version" in item:
            chunk_data["version"] = item["version"]

        all_chunks.append(chunk_data)
    return all_chunks


# 2a. Helper: Split text into overlapping chunks
def chunk_text(text, chunk_size, overlap):
    length = len(text)
    chunks = []
    start = 0
    while start < length:
        end = start + chunk_size
        if end > length:
            end = length
        chunks.append(text[start:end])
        start = end - overlap
        if end == length:
            break
    return chunks


    db_hashes = []
    logging.info(f"{url},{chunks[0]['chunk_hash']}")

    # if Site
            models.IsEmptyCondition(is_empty=models.PayloadField(key="source_url")),
            models.FieldCondition(key="url", match=models.MatchValue(value=url)),
        ]
    )

    # if Linked Document
    link_filter = None
    if chunk_source_url:
        link_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="source_url", match=models.MatchValue(value=chunk_source_url)
                ),
                models.FieldCondition(key="url", match=models.MatchValue(value=url)),
            ]
        )

    # Hash filter
    chunk_hashes = [chunk["chunk_hash"] for chunk in chunks]
    hash_filter = models.Filter(
        must=[
            models.HasIdCondition(has_id=chunk_hashes),
        ],
    )

    if link_filter:
        qdrant_filter = models.Filter(should=[url_filter, link_filter, hash_filter])
    else:
        qdrant_filter = models.Filter(should=[url_filter, hash_filter])

    db_points, _ = qdrant_client.scroll(
        collection_name=COLLECTION_NAME, scroll_filter=qdrant_filter, limit=3000
    )

    for point in db_points:
        point_id = point.id
        point_url = point.payload.get("url")
        db_hash = {"id": point_id, "url": point_url}
        source_url = point.payload.get("source_url")
        if source_url is not None:
            db_hash["source_url"] = source_url
        db_hashes.append(db_hash)

    logging.info(
        f"Database Hashes found for url: {db_hashes}, {len(db_hashes)} stycken"
    )

    return db_hashes


# 4. Determine which chunks are new and need to be updated
def get_new_chunks(new_chunks, db_hashes):
    if not new_chunks:
        logging.info("Empty input data - no chunks to update")
        return

    db_hashes_set = {db_point["id"] for db_point in db_hashes}

    urls_needing_update = {
        chunk["url"] for chunk in new_chunks if chunk["chunk_hash"] not in db_hashes_set
    }

    chunks_to_update = [
        chunk for chunk in new_chunks if chunk["url"] in urls_needing_update
    ]

    logging.info(
        f"Found {len(urls_needing_update)} URLs needing update with {len(chunks_to_update)} total chunks"
    )
    logging.info(f"URLs to update: {urls_needing_update}")

    return chunks_to_update


# 5. Find URLs/documents that are no longer present and should be removed
def get_old_urls(new_chunks, db_hashes):
    db_urls_set = {db_point["url"] for db_point in db_hashes}
    new_urls_set = {chunk["url"] for chunk in new_chunks}

    removed_urls = db_urls_set - new_urls_set

    return removed_urls if removed_urls else None


# 6. Create embeddings for the new chunks and calculate cost
def create_embeddings(chunks):
    texts = [chunk["chunk"] for chunk in chunks]
    embeddings = []
    total_cost_sek = 0
    for batch_start in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[batch_start : batch_start + BATCH_SIZE]
        response = openai.Embedding.create(model=EMBEDDING_MODEL, input=batch_texts)

        batch_cost_sek = calculate_cost_sek(batch_texts)
        total_cost_sek += batch_cost_sek

        batch_embeddings = [e["embedding"] for e in response["data"]]
        embeddings.extend(batch_embeddings)
        time.sleep(SLEEP_TIME)
    return embeddings, total_cost_sek


# 7. Remove old data points from Qdrant that has new/are updating
def remove_old_datapoints(new_chunks, old_urls=None):
    # Remove url datapoints
    urls = [chunk["url"] for chunk in new_chunks]
    if old_urls:
        urls.extend(old_urls)

    url_filter = models.Filter(
        must=[models.FieldCondition(key="url", match=models.MatchAny(any=urls))]
    )

    points_selector = models.FilterSelector(filter=url_filter)

    qdrant_client.delete(
        collection_name=COLLECTION_NAME, points_selector=points_selector
    )
    logging.info("Removed OLD datapoints")


# 8. Upsert (insert/update) the new/updated chunks and their embeddings into Qdrant
def upsert_to_qdrant(chunks, embeddings):
    points = []
    for i, chunk in enumerate(chunks):
        utc_time = datetime.now(timezone.utc).replace(microsecond=0)
        update_time = utc_time.astimezone(ZoneInfo("Europe/Stockholm"))
        update_time_str = update_time.strftime("%Y-%m-%dT%H:%M:%S")
        payload = {
            "url": chunk["url"],
            "title": chunk["title"],
            "chunk": chunk["chunk"],
            "chunk_info": chunk["chunk_info"],
            "update_date": update_time_str,
        }
        if "source_url" in chunk:
            payload["source_url"] = chunk["source_url"]

        if "version" in chunk:
            payload["version"] = chunk["version"]

        point = PointStruct(
            id=chunk["chunk_hash"], vector=embeddings[i], payload=payload
        )

        logging.info(f"Chunk uppladdas: {chunk['chunk_hash']}, URL: {chunk['url']}")
        points.append(point)
    try:
        qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
    except Exception as e:
        logging.error(f"Upsert failed: {e}")


# Main function, Update a url and its pdfs(For multiusage setup driver outside)
def update_url_qdrant(url, providedTitle=None):
    kwargs = {}
    if providedTitle is not None:
        kwargs["providedTitle"] = providedTitle

    page_data = get_page_details(url, driver, **kwargs)

    point_count = 0
    total_update_cost_SEK = 0
    for data_point in page_data:
        point_count += 1
        logging.info(f"{point_count} av {len(page_data)}")
        total_update_cost_SEK += process_item_qdrant(data_point)

    logging.info(f"Total Qdrant URL Update Cost = {total_update_cost_SEK} SEK")
    return total_update_cost_SEK


# Main execution starts here
load_dotenv(dotenv_path="/app/data/API_KEYS.env")
qdrant_api_key = os.getenv("QDRANT_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

qdrant_client = QdrantClient(
    url=QDRANT_URL, port=QDRANT_PORT, https=True, api_key=qdrant_api_key
)
openai.api_key = openai_api_key

## WebDriver
driver = setup_driver()

# Skapa collection eller hämta till client
try:
    qdrant_client.get_collection(COLLECTION_NAME)
except Exception:
    vectors_config = VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
    qdrant_client.recreate_collection(
        collection_name=COLLECTION_NAME, vectors_config=vectors_config
    )
