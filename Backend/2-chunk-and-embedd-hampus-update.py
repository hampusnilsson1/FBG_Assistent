import os
import json
import time
import datetime
import uuid
import hashlib
from dotenv import load_dotenv
import streamlit as st
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    VectorParams, Distance, PointStruct
)
from openai import OpenAI
import tiktoken

# Constants
QDRANT_URL = "https://qdrant.utvecklingfalkenberg.se"
QDRANT_PORT = 443
EMBEDDING_MODEL = "text-embedding-3-large"  # Using the larger model
BATCH_SIZE = 1000
SLEEP_TIME = 1
VECTOR_SIZE = 3072  # Updated vector size for large embeddings
COLLECTION_NAME = "FalkenbergsKommunsHemsida"

### *** HAMPUS GÖR NYTT TEST *** ###
##--------------------------------##
##
#UUID Gen
def generate_uuid(text):
    hash_object = hashlib.md5(text.encode())
    return str(uuid.UUID(hash_object.hexdigest()))


#Token Count/Calc
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

# Förra
# 1. Scrappa sidan till en fil.(Text,URL,Last Modified)


# Denna
## 1. Kolla scrappade fil och jämför varje punkt med den gamla cache scrap datan.
#    Först Last_modified där url är samma i filerna, Olika nya last_modifed > gamla
#       Då Uppdatera variabel/cachefil sedan
def update_qdrant():
    total_update_cost_SEK = 0
    with open("scraped_data.json", "r", encoding="utf-8") as new_file:
        new_data = json.load(new_file)

    try:
        with open("scraped_data_cache.json", "r", encoding="utf-8") as cache_file:
            cache_data = json.load(cache_file)
    except FileNotFoundError:
        cache_data = []

    cache_dict = {item["url"]: item for item in cache_data}
    updated_items = []

    for new_item in new_data:
        new_url = new_item["url"]
        new_last_modified_str = new_item["last_modified"]
        new_last_modified = datetime.datetime.fromisoformat(
            new_last_modified_str.replace("Z", "+00:00")
        )

        if new_url in cache_dict:
            old_item = cache_dict[new_url]
            old_last_modified_str = old_item["last_modified"]
            old_last_modified = datetime.datetime.fromisoformat(
                old_last_modified_str.replace("Z", "+00:00")
            )

            if new_last_modified > old_last_modified:
                if new_item["texts"] != old_item["texts"]:
                    # Deletes if new available
                    delete_qdrant_embedd(new_item)
                    print(f"Uppdaterad sida: {new_url}")
                    updated_items.append(new_item)
        else:
            print(f"Ny sida hittad: {new_url}")
            updated_items.append(new_item)

    for item in updated_items:
        #Turn to chunk, embedd and upsert to qdrant.
        chunks = get_item_chunks(item)
        embeddings, chunk_cost_SEK = create_embeddings(chunks)
        total_update_cost_SEK += chunk_cost_SEK
        upsert_to_qdrant(chunks, embeddings)

    # Uppdatera cache-filen
    with open("scraped_data_cache.json", "w", encoding="utf-8") as cache_file:
        json.dump(new_data, cache_file, indent=4)
    
    print("Total Qdrant Update Cost =", total_update_cost_SEK,"SEK")
    return total_update_cost_SEK


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
        response = openai_client.embedding.create(
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
        points.append(point)
    qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )

# Main execution starts here
load_dotenv()
qdrant_api_key = os.getenv("QDRANT_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

qdrant_client = QdrantClient(
    url=QDRANT_URL, port=QDRANT_PORT, https=True, api_key=qdrant_api_key
)
openai_client = OpenAI(api_key=openai_api_key)

# Skapa collection eller hämta till client
try:
    qdrant_client.get_collection(COLLECTION_NAME)
except Exception:
    print(f"Collection {COLLECTION_NAME} not found. Creating new collection.")
    vectors_config = VectorParams(
        size=VECTOR_SIZE,
        distance=Distance.COSINE
    )
    qdrant_client.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=vectors_config
    )

update_qdrant()