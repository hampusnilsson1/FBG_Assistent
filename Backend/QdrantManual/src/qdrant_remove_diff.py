import os
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.http import models

# Ladda API-nyckel från .env-fil
load_dotenv(dotenv_path="../../data/API_KEYS.env")
qdrant_api_key = os.getenv("QDRANT_API_KEY")

QDRANT_URL = "https://qdrant.utvecklingfalkenberg.se/"
QDRANT_PORT = 443
COLLECTION_NAME = "FalkenbergsKommunsHemsida"

qdrant_client = QdrantClient(
    url=QDRANT_URL, port=QDRANT_PORT, https=True, api_key=qdrant_api_key
)


# Hämta alla punkter från Qdrant
def get_qdrant_urls():
    url = f"{QDRANT_URL}collections/{COLLECTION_NAME}/points/scroll"
    headers = {"api-key": qdrant_api_key, "Content-Type": "application/json"}
    payload = {"with_payload": True, "limit": 50000}

    results = []
    scroll_id = None

    while True:
        if scroll_id:
            payload["offset"] = scroll_id

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            print("Timeout inträffade. Försöker igen.")
            continue
        except requests.exceptions.RequestException as e:
            print(f"Ett förfrågningsfel inträffade: {e}")
            break

        if not response.text.strip():
            print("Tomt svar från servern. Avslutar.")
            break

        try:
            data = response.json()
        except ValueError as e:
            print("JSON-avkodningsfel:", e)
            break

        points = data.get("result", {}).get("points", [])
        if not points:
            print("Inga fler punkter att scrolla.")
            break

        for point in points:
            try:
                payload = point.get("payload", {})
                url = payload.get("url", None)
                source_url = payload.get("source_url", None)
                if not url:
                    print("Varning: Punkt saknar URL. Hoppar över.")
                    continue
                if source_url or "evolution" in url:
                    continue  # Ignorera URL:er som slutar på .pdf , är länkade document eller evolution document

                results.append(url)
            except Exception as e:
                print(f"Fel vid bearbetning av punkt: {e}. Hoppar över.")
                continue

        scroll_id = data.get("result", {}).get("next_page_offset")
        if not scroll_id:
            print("Scroll-id saknas, ingen mer data att hämta.")
            break

    return set(results)


# Hämta URL:er från sitemap
def get_sitemap_urls(sitemap_url):
    response = requests.get(sitemap_url)
    if response.status_code == 200:
        sitemap = ET.fromstring(response.content)
        urls = set(
            url_elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc").text
            for url_elem in sitemap.findall(
                ".//{http://www.sitemaps.org/schemas/sitemap/0.9}url"
            )
        )
        return urls
    else:
        raise Exception(f"Failed to fetch sitemap from {sitemap_url}")


def remove_qdrant_urls(urls):
    qdrant_filter = models.Filter(
        should=[
            models.FieldCondition(key="url", match=models.MatchAny(any=urls)),
            models.FieldCondition(key="source_url", match=models.MatchAny(any=urls)),
        ]
    )

    points_selector = models.FilterSelector(filter=qdrant_filter)

    qdrant_client.delete(
        collection_name=COLLECTION_NAME, points_selector=points_selector
    )


# Huvudfunktion för att jämföra URL:er
def main():
    sitemap_url = (
        "https://kommun.falkenberg.se/index.php?option=com_jmap&view=sitemap&format=xml"
    )

    try:
        qdrant_urls = get_qdrant_urls()
        sitemap_urls = get_sitemap_urls(sitemap_url)

        # Hitta URL:er som finns i Qdrant men inte i sitemap
        missing_urls = qdrant_urls - sitemap_urls

        if missing_urls:
            print("URL:er som finns i Qdrant men inte i sitemap:")
            for url in missing_urls:
                print(url)
        else:
            print("Alla URL:er i Qdrant finns också i sitemap.")

        print(f"Antal URL:er hittade i Qdrant: {len(qdrant_urls)}")
        print(f"Antal URL:er i sitemap: {len(sitemap_urls)}")
        print(f"Antal saknade URL:er: {len(missing_urls)}")
        print(missing_urls)

        agree_remove = input("Är du säker på att du vill ta bort dessa?(y/n)")
        if agree_remove.lower() == "y":
            remove_qdrant_urls(missing_urls)
            print("Urls removed!")

    except Exception as e:
        print(f"Ett fel inträffade: {e}")


if __name__ == "__main__":
    main()
