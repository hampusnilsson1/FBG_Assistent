import pytz
import requests
import os
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from qdrant_client import QdrantClient
from individual_scrap_update_qdrant import update_url_qdrant
from qdrant_client import models
import xml.etree.ElementTree as ET

QDRANT_URL = "https://qdrant.utvecklingfalkenberg.se"
QDRANT_PORT = 443
COLLECTION_NAME = "FalkenbergsKommunsHemsida"

# Setup
load_dotenv(dotenv_path="../../data/API_KEYS.env")
qdrant_api_key = os.getenv("QDRANT_API_KEY")

qdrant_client = QdrantClient(
    url=QDRANT_URL,
    port=QDRANT_PORT,
    https=True,
    api_key=qdrant_api_key,
)

# Hämta alla URLs utan lastmod från sitemapen
sitemap_url = (
    "https://kommun.falkenberg.se/index.php?option=com_jmap&view=sitemap&format=xml"
)
response = requests.get(sitemap_url)

if response.status_code == 200:
    # Parse the XML content
    root = ET.fromstring(response.content)
    namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    nolastmod_site = []
    for url in root.findall("ns:url", namespace):
        loc = url.find("ns:loc", namespace).text
        lastmod_elem = url.find("ns:lastmod", namespace)
        if lastmod_elem is None:
            nolastmod_site.append(loc)
            print(f"URL utan lastmod: {loc}")
    print(f"{len(nolastmod_site)} sidor totalt utan lastmod")

    # Hämta alla datapunkter från Qdrant-databasen
    qdrant_filter = models.Filter(
        must_not=[
            models.FieldCondition(key="url", match=models.MatchText(text="evolution"))
        ],
        must=[models.IsEmptyCondition(is_empty=models.PayloadField(key="source_url"))],
    )

    obj_qdrant_data, next_page_offset = qdrant_client.scroll(
        collection_name=COLLECTION_NAME,
        limit=100,
        scroll_filter=qdrant_filter,
    )

    while next_page_offset is not None:
        new_data, next_page_offset = qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=qdrant_filter,
            limit=100,
            offset=next_page_offset,
        )
        obj_qdrant_data.extend(new_data)

    qdrant_datapunkter = []
    if obj_qdrant_data:
        for datapunkt in obj_qdrant_data:
            url = datapunkt.payload.get("url")
            date = datapunkt.payload.get("update_date")
            qdrant_datapunkter.append({"url": url, "update_date": date})

        qdrant_site = []
        for datapunkt in qdrant_datapunkter:
            if not datapunkt["update_date"]:
                continue
            try:
                update_date = datetime.strptime(
                    datapunkt["update_date"], "%Y-%m-%dT%H:%M:%S"
                )
            except:
                try:
                    update_date = datetime.strptime(
                        datapunkt["update_date"], "%Y-%m-%d"
                    )
                except:
                    try:
                        update_date = datetime.strptime(
                            datapunkt["update_date"], "%Y-%m-%dT%H:%M:%SZ"
                        )
                    except:
                        print("Failed To Convert point date")
                        continue
                        # Om datumsträngen inte kan konverteras, hoppa över den här datapunkten

            update_date = update_date.replace(tzinfo=pytz.utc)
            if update_date < datetime.now(pytz.utc) - timedelta(days=15):
                print(f"{datapunkt["url"]},{datapunkt["update_date"]} tillåten att uppdateras")
                qdrant_site.append(
                    {"url": datapunkt["url"], "update_date": update_date}
                )

        nolastmod_urls = set(nolastmod_site)
        qdrant_urls = set(site["url"] for site in qdrant_site)
        print()

        sites_to_update = []
        added_urls = set()
        for site in qdrant_site:
            if site["url"] in nolastmod_urls and site["url"] not in added_urls:
                sites_to_update.append(site)
                added_urls.add(site["url"])
        print(f"{len(sites_to_update)} sidor som är äldre än 15 dagar")
        
        # Fråga användaren om de vill uppdatera
        if sites_to_update:
            for url in sites_to_update:
                logging.info(url)
            logging.info(f"Hittade {len(sites_to_update)} sidor som är äldre än sagd")
            are_u_sure = input(
                "Är du säker på att du vill uppdatera dessa sidor? (y/n)"
            )
            if are_u_sure.lower() == "y":
                # Uppdatera de sidor som är äldre än 7 dagar sen
                for url in sites_to_update:
                    update_url_qdrant(url)
                    logging.info(f"Uppdaterade {url}")
            else:
                logging.info("Uppdatering avbruten.")
        else:
            logging.info("Inga sidor att uppdatera.")
