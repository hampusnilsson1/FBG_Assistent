import os
import time
import uuid
import hashlib
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    VectorParams, Distance, PointStruct
)
import openai
import tiktoken

from bs4 import BeautifulSoup
import re
import requests
from selenium import webdriver
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
SLEEP_TIME = 1
VECTOR_SIZE = 3072  # Updated vector size for large embeddings
COLLECTION_NAME = "FalkenbergsKommunsHemsida"

# LOGGING------------------
# Konfigurera logging för att skriva till en fil
logging.basicConfig(filename='individual_LOGG.txt', level=logging.INFO, format='%(message)s')

# Skapa en handler för att också skriva till konsolen
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

# Använd logging istället för logging.info
logging.info("Detta kommer att skrivas till både konsolen och filen")
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
    # Hämta antalet tokens
    num_tokens = count_tokens(texts, model)

    # Kostnadsberäkningar per 1000 tokens
    if model == "text-embedding-3-large":
        cost_per_1000_tokens = 0.00013  # USD
    else:
        raise ValueError("Unsupported model")

    # Beräkna kostnaden
    cost = ((num_tokens / 1000) * cost_per_1000_tokens) * SEK_per_USD # to return SEK
    return cost


### Scrappa individuell sida och dess pdfer
def setup_driver():
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.headless = True  # Kör i headless-läge
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def fetch_pdf_content(pdf_url):
    pdf_file_path = 'temp.pdf'
    try:
        response = requests.get(pdf_url)
        response.raise_for_status()

        with open(pdf_file_path, 'wb') as f:
            f.write(response.content)
        
        text_content = []
        with pdfplumber.open(pdf_file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_content.append(page_text)
        
        return ' '.join(text_content) if text_content else 'No text found in PDF'
    except (requests.exceptions.RequestException, Exception) as e:
        logging.info(f"Error fetching or processing PDF from {pdf_url}: {str(e)}")
        return 'Error fetching or processing PDF'
    finally:
        if os.path.exists(pdf_file_path):
            os.remove(pdf_file_path)

def fetch_sitemap(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.content

def get_page_details(url, driver):
    # Fetch the page content
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
        
    results = []

    results.append({
        "url": url,
        "title": title,
        "texts": texts
    })

    pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.IGNORECASE))
    for link in pdf_links:
        pdf_url = link['href']
        if pdf_url.startswith('/'):
            pdf_url = 'https://kommun.falkenberg.se' + pdf_url
            
        pdf_text = fetch_pdf_content(pdf_url)
        results.append({
            "url": pdf_url,
            "title": link.text.strip() or "No title",
            "texts": pdf_text,
            "source_url": url
        })
        
    return results

def get_url_details(target_url, sitemap_url, driver):
    # Fetch and parse the sitemap
    xml_data = fetch_sitemap(sitemap_url)
    root = ET.fromstring(xml_data)
    ns = {'sitemaps': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    
    # Search for the specific URL in the sitemap
    last_modified = None
    for url_elem in root.findall(".//sitemaps:url", ns):
        loc_elem = url_elem.find("sitemaps:loc", ns)
        if loc_elem is not None and loc_elem.text == target_url:
            lastmod_elem = url_elem.find("sitemaps:lastmod", ns)
            last_modified = lastmod_elem.text if lastmod_elem is not None else "No Last Modified Found"
            break

    # Fetch page details (title and texts)
    page_data = get_page_details(target_url, driver)
    for data_point in page_data:
        data_point["last_modified"] = last_modified
        
    return page_data
            

# Processa en datapunkt 
def process_item_qdrant(item):
    logging.info("Dividing to chunks")
    chunks = get_item_chunks(item)
    logging.info("Dividing to chunks Done")
    logging.info("Embedding chunks")
    embeddings, chunk_cost_SEK = create_embeddings(chunks)
    logging.info("Embedding chunks Done This cost: ",chunk_cost_SEK,"SEK")
    logging.info("Uploading Embeddings")
    upsert_to_qdrant(chunks, embeddings)
    logging.info("Uploading Embeddings Done")
    return chunk_cost_SEK



## 2. Om något i de olika "texter" för url ändrats så dela scrappade datan in till nya chunks och Embedda dessa.
def delete_qdrant_embedd(new_item):
    # Med "new_item" ta bort gamla datapunkter med samma url.
    new_item_url = new_item["url"]

    qdrant_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="url", match=models.MatchValue(value=new_item_url)
            )
        ]
    )

    qdrant_client.delete(collection_name=COLLECTION_NAME, filter=qdrant_filter)


## 3. Dela in texten i chunks/batches indexerade och formaterade
def get_item_chunks(item):
    all_chunks = []
    text_chunks = chunk_text(item["texts"], 4000, 300)
    num_chunks = len(text_chunks)
    for index, chunk in enumerate(text_chunks):
        chunk_data = {
            "url": item["url"],
            "title": item["title"],
            "chunk": chunk,
            "chunk_info": f"Chunk {index + 1} of {num_chunks}",
        }
        all_chunks.append(chunk_data)
    return all_chunks


# Delar in i chunks/batches
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

## 4. Gör om chunks till embeddnings
def create_embeddings(chunks):
    texts = [chunk["chunk"] for chunk in chunks]
    embeddings = []
    total_cost_sek = 0
    for batch_start in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[batch_start:batch_start + BATCH_SIZE]
        response = openai.Embedding.create(
            model=EMBEDDING_MODEL,
            input=batch_texts
        )
        
        batch_cost_sek = calculate_cost_sek(batch_texts)
        total_cost_sek += batch_cost_sek
        
        batch_embeddings = [e["embedding"] for e in response["data"]]
        embeddings.extend(batch_embeddings)
        time.sleep(SLEEP_TIME)
    return embeddings, total_cost_sek


## 5. Sätt in i Qdrant.
def upsert_to_qdrant(chunks, embeddings):
    points = []
    for i, chunk in enumerate(chunks):
        doc_uuid = generate_uuid(chunk["chunk"])
        point = PointStruct(
            id=doc_uuid,
            vector=embeddings[i],
            payload={
                "url": chunk["url"],
                "title": chunk["title"],
                "chunk": chunk["chunk"],
                "chunk_info": chunk["chunk_info"],
            }
        )
        
        logging.info("Chunk uppladdas: ",doc_uuid, "URL",chunk["url"])
        points.append(point)
    qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )

# Main function, Update a url and its pdfs(For multiusage setup driver outside)
def update_url_qdrant(url):
    driver = setup_driver()
    sitemap_url = "https://kommun.falkenberg.se/index.php?option=com_jmap&view=sitemap&format=xml"
    total_update_cost_SEK = 0
    
    page_data = get_url_details(url,sitemap_url,driver)
    
    # Delete old datapoint in database
    try:
        delete_qdrant_embedd(page_data[0])
        logging.info("Deleted current point in database")
    except:
        logging.info("Deleting failed, List is empty!")
        
    for data_point in page_data:
        total_update_cost_SEK += process_item_qdrant(data_point)

    
    logging.info("Total Qdrant URL Update Cost =", total_update_cost_SEK,"SEK")
    return total_update_cost_SEK


# Main execution starts here
load_dotenv(dotenv_path="API_KEYS.env")
qdrant_api_key = os.getenv("QDRANT_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

qdrant_client = QdrantClient(
    url=QDRANT_URL, port=QDRANT_PORT, https=True, api_key=qdrant_api_key
)
openai.api_key = openai_api_key

# Skapa collection eller hämta till client
try:
    qdrant_client.get_collection(COLLECTION_NAME)
except Exception:
    vectors_config = VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
    qdrant_client.recreate_collection(collection_name=COLLECTION_NAME, vectors_config=vectors_config)

#update_url_qdrant("https://kommun.falkenberg.se/bygga-bo-och-miljo/bygga/skyddade-och-bevarandevarda-byggnader")
#time.sleep(100) # Wait to not spamm
