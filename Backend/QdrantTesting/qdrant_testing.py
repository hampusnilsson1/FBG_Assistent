import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models


QDRANT_URL = "https://qdrant.utvecklingfalkenberg.se"
QDRANT_PORT = 443
COLLECTION_NAME = "FalkenbergsKommunsHemsida"

load_dotenv(dotenv_path="../data/API_KEYS.env")
qdrant_api_key = os.getenv("QDRANT_API_KEY")

qdrant_client = QdrantClient(
    url=QDRANT_URL, port=QDRANT_PORT, https=True, api_key=qdrant_api_key
)

def search_exactmatch(url):
    qdrant_filter = models.Filter(
        should=[
            models.FieldCondition(key="url", match=models.MatchValue(value=url)),
            models.FieldCondition(key="source_url", match=models.MatchValue(value=url)),
        ]
    )

    # Perform the search
    search_result, _ = qdrant_client.scroll(
        collection_name=COLLECTION_NAME, scroll_filter=qdrant_filter, limit=1000
    )

    return search_result

def search_partialmatch(url):
    qdrant_filter = models.Filter(
        should=[
            models.FieldCondition(key="url", match=models.MatchText(text=url)),
            models.FieldCondition(key="source_url", match=models.MatchText(text=url)),
        ]
    )

    # Perform the search
    search_result, _ = qdrant_client.scroll(
        collection_name=COLLECTION_NAME, scroll_filter=qdrant_filter, limit=1000
    )

    return search_result

def print_result(result):
    for point in result:
            id = point.id
            chunk = point.payload.get('chunk', "")[:500]
            chunk_info = point.payload.get('chunk_info', "")
            title = point.payload.get('title', "")
            url = point.payload.get('url', "")
            source_url = point.payload.get('source_url', "")
            update_date = point.payload.get('update_date', "")
            print(f"**{title}**")
            print(f"ID: {id}")
            print(f"Chunk: {chunk}")
            print(f"Chunk_info: {chunk_info}")
            print(f"URL: {url}")
            print(f"Source URL: {source_url}")
            print(f"Update Date: {update_date}")
            print("-" * 50)
    print(f"Totalt {len(result)} datapunkter hittades.")

print("-" * 50)
print("Welcome to the Qdrant Search Application!")
print("Used for testing Qdrant API and searching for datapoints.")
while True:
    input_url = input("1. Search for Exact URL/Source URL Match \n2. Search for datapoints including input\n3. Exit Application\n")
    print("-" * 50)
    if input_url == "1":
        print("Search for Exact URL/Source URL Match")
        url = str(input("Enter the URL to search for: "))
        result = search_exactmatch(url)
        print(f"Search results for {url}:")
        print_result(result)
            
    elif input_url == "2":
        print("Search for datapoints including input")
        url = str(input("Enter the URL to search for: "))
        result = search_partialmatch(url)
        print(f"Search results for {url}:")
        print_result(result)
            
    elif input_url == "3":
        print("Exiting the application.")
        break