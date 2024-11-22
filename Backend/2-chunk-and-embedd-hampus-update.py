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
from qdrant_client.http.models import VectorParams, Distance
from openai import OpenAI

# Constants
QDRANT_URL = "https://qdrant.utvecklingfalkenberg.se"
QDRANT_PORT = 443
EMBEDDING_MODEL = "text-embedding-3-large"  # Using the larger model
BATCH_SIZE = 1000
SLEEP_TIME = 1
VECTOR_SIZE = 3072  # Updated vector size for large embeddings
COLLECTION_NAME = "FalkenbergsKommunsHemsida"


def generate_uuid(chunk):
    hash_object = hashlib.md5(chunk.encode())
    return str(uuid.UUID(hash_object.hexdigest()))


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
    st.write(f"Collection {COLLECTION_NAME} not found. Creating new collection.")
    vectors_config = VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
    qdrant_client.recreate_collection(
        collection_name=COLLECTION_NAME, vectors_config=vectors_config
    )

# Öppna senaste scraped file och gör om
with open("scraped_data.json", "r", encoding="utf-8") as file:
    data = json.load(file)

all_chunks = []
for item in data:
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


upserted_documents_count = 0
for batch_start in range(0, len(all_chunks), BATCH_SIZE):
    batch_data = all_chunks[batch_start : batch_start + BATCH_SIZE]
    batch = [item["chunk"] for item in batch_data]
    response = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
    batch_embeddings = [e.embedding for e in response.data]

    for i, chunk in enumerate(batch):
        embeddings = batch_embeddings[i]
        doc_uuid = generate_uuid(chunk)
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                {
                    "id": doc_uuid,
                    "vector": embeddings,
                    "payload": {
                        "url": batch_data[i][
                            "url"
                        ],  # This still assumes 'item' is in scope
                        "title": batch_data[i]["title"],
                        "chunk": chunk,
                    },
                }
            ],
        )
        upserted_documents_count += 1
        if upserted_documents_count % 100 == 0:
            print(
                f"Upserted {upserted_documents_count} documents into '{COLLECTION_NAME}' collection."
            )
    time.sleep(SLEEP_TIME)

print(f"Finished upserting. Total documents upserted: {upserted_documents_count}")

### *** HAMPUS GÖR NYTT TEST *** ###
##--------------------------------##

# Förra
# 1. Scrappa sidan till en fil.(Text,URL,Last Modified)


# Denna
# 1. Kolla scrappade fil och jämför varje punkt med den gamla cache scrap datan.
#    Först Last_modified där url är samma i filerna, Olika nya last_modifed > gamla
#       Då Uppdatera variabel/cachefil sedan
def load_data():
    with open("scraped_data.json", "r", encoding="utf-8") as new_file:
        new_data = json.load(new_file)

    with open("scraped_data_cache.json", "r", encoding="utf-8") as cache_file:
        cache_data = json.load(cache_file)

    cache_dict = {}
    for old_item in cache_data:
        old_url = old_item["url"]
        cache_dict[old_url] = old_item

    for new_item in new_data:
        new_url = new_item["url"]
        new_last_modified_str = new_item["last_modified"]
        new_last_modified = datetime.fromisoformat(
            new_last_modified_str.replace("Z", "+00:00")
        )

        if new_url in cache_dict:
            old_item = cache_dict[new_url]
            old_last_modified_str = old_item["last_modified"]
            old_last_modified = datetime.fromisoformat(
                old_last_modified_str.replace("Z", "+00:00")
            )

            if new_last_modified > old_last_modified:
                if (
                    new_item["texts"] != old_item["texts"]
                ):  # Om det är skillnad i texterna så uppdatera
                    delete_qdrant_embedd(new_item)

                    print(
                        f"Du har hittat en ny uppdatering av en sida: {new_url}"
                    )  # Uppdatera cachen! då en ny uppdatering i databas kommer göras och loggas i cachen.
        else:
            print(f"Ny sida hittad: {new_url}")  # GÖR NY EMBEDD OCH SPARA I DATABAS.

    # I slutet (HÄR) uppdatera cache filen med senaste uppdateringen.
    # scraped_data_cache.json


# 2. Om något i de olika "texter" för url ändrats så dela scrappade datan in till nya chunks och Embedda dessa.
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

    qdrant_client.delete(collection_name={COLLECTION_NAME}, filter=qdrant_filter)


##  Dela in texten i chunks/batches indexerade och formaterade
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

    # Gör om chunks till embeddnings

    # Sätt in i Qdrant.
