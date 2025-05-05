import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import PointStruct

# Qdrant Connection
QDRANT_URL = "https://qdrant.utvecklingfalkenberg.se"
QDRANT_PORT = 443
COLLECTION_NAME = "FalkenbergsKommunsHemsida"

load_dotenv(dotenv_path="/app/data/API_KEYS.env")
qdrant_api_key = os.getenv("QDRANT_API_KEY")

qdrant_client = QdrantClient(
    url=QDRANT_URL, port=QDRANT_PORT, https=True, api_key=qdrant_api_key
)


def remove_qdrant(url):
    qdrant_filter = models.Filter(
        should=[
            models.FieldCondition(key="url", match=models.MatchValue(value=url)),
            models.FieldCondition(key="source_url", match=models.MatchValue(value=url)),
        ]
    )

    points_selector = models.FilterSelector(filter=qdrant_filter)

    deleted_points = qdrant_client.scroll(
        collection_name=COLLECTION_NAME, scroll_filter=qdrant_filter, limit=1000
    )

    qdrant_client.delete(
        collection_name=COLLECTION_NAME, points_selector=points_selector
    )
    
    # Ta bort nuvarande länk om den har fler
    scroll_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="source_url",
                match=models.MatchText(text=url),
            )
        ]
    )
    results, _ = qdrant_client.scroll(collection_name=COLLECTION_NAME, scroll_filter=scroll_filter)
    for point in results:
        old_source_url = point.payload.get("source_url", "")
        new_source_url = ",".join(
            [link for link in old_source_url.split(",") if link != url]
        )
        point.payload["source_url"] = new_source_url
        try:
            qdrant_client.update(
                collection_name=COLLECTION_NAME,
                points=[
                    PointStruct(
                        id=point.id,
                        vector=point.vector,
                        payload=point.payload,
                    )
                ],
            )
            print(f"Updated point: {point.id}, old source_url: {old_source_url}, new source_url: {new_source_url}")
        except Exception as e:
            print(f"Failed to update point: {point.id}, error: {e}")

    return deleted_points
