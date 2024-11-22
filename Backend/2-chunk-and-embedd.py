import os
import json
import time
import uuid
import hashlib
from dotenv import load_dotenv
import streamlit as st
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance
from openai import OpenAI

# Constants
QDRANT_URL = 'https://qdrant.utvecklingfalkenberg.se'
QDRANT_PORT = 443
EMBEDDING_MODEL = "text-embedding-3-large"  # Using the larger model
BATCH_SIZE = 1000
SLEEP_TIME = 1
VECTOR_SIZE = 3072  # Updated vector size for large embeddings
COLLECTION_NAME = 'FalkenbergsKommunsHemsida'

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
qdrant_api_key = os.getenv('qdrant_api_key')
openai_api_key = os.getenv('openai_api_key')

qdrant_client = QdrantClient(url=QDRANT_URL, port=QDRANT_PORT, https=True, api_key=qdrant_api_key)
openai_client = OpenAI(api_key=openai_api_key)

try:
    qdrant_client.get_collection(COLLECTION_NAME)
except Exception:
    st.write(f"Collection {COLLECTION_NAME} not found. Creating new collection.")
    vectors_config = VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
    qdrant_client.recreate_collection(collection_name=COLLECTION_NAME, vectors_config=vectors_config)

with open('scraped_data.json', 'r', encoding='utf-8') as file:
    data = json.load(file)

all_chunks = []
for item in data:
        text_chunks = chunk_text(item['texts'], 4000, 300)
        num_chunks = len(text_chunks)
        for index, chunk in enumerate(text_chunks):
            chunk_data = {
                'url': item['url'],
                'title': item['title'],
                'chunk': chunk,
                'chunk_info': f'Chunk {index + 1} of {num_chunks}'
            }
            all_chunks.append(chunk_data)


upserted_documents_count = 0
for batch_start in range(0, len(all_chunks), BATCH_SIZE):
    batch_data = all_chunks[batch_start:batch_start + BATCH_SIZE]
    batch = [item['chunk'] for item in batch_data]
    response = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
    batch_embeddings = [e.embedding for e in response.data]

    for i, chunk in enumerate(batch):
        embeddings = batch_embeddings[i]
        doc_uuid = generate_uuid(chunk)
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=[{
                "id": doc_uuid,
                "vector": embeddings,
                "payload": {
                    "url": batch_data[i]['url'],  # This still assumes 'item' is in scope
                    "title": batch_data[i]['title'],
                    "chunk": chunk
                }
            }]
        )
        upserted_documents_count += 1
        if upserted_documents_count % 100 == 0:
            print(f"Upserted {upserted_documents_count} documents into '{COLLECTION_NAME}' collection.")
    time.sleep(SLEEP_TIME)

print(f"Finished upserting. Total documents upserted: {upserted_documents_count}")
