import requests
import os
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

# Funktion hämtas från fil
import individual_scrap_update_qdrant
from individual_scrap_update_qdrant import update_url_qdrant

QDRANT_URL = "https://qdrant.utvecklingfalkenberg.se"
QDRANT_PORT = 443
COLLECTION_NAME = "FalkenbergsKommunsHemsida"

logging.basicConfig(
    filename="../data/Price_update.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def update_qdrant_since(update_since):
    update_since_datetime = datetime.strptime(update_since, "%Y-%m-%d")
    url = (
        "https://kommun.falkenberg.se/index.php?option=com_jmap&view=sitemap&format=xml"
    )
    response = requests.get(url)

    if response.status_code == 200:
        # Parse the XML content
        root = ET.fromstring(response.content)

        namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        urls = []
        new_urls = []
        urls_no_update_date = []
        update_urls = []
        urls_no_lastmod = []
        for url in root.findall("ns:url", namespace):
            loc = url.find("ns:loc", namespace).text
            lastmod_elem = url.find("ns:lastmod", namespace)
            if lastmod_elem is not None and lastmod_elem.text is not None:
                lastmod = lastmod_elem.text
                try:

                    lastmod_datetime = datetime.strptime(lastmod, "%Y-%m-%dT%H:%M:%SZ")
                except ValueError as e:
                    print(f"Felaktigt datumformat i lastmod {lastmod}: {e}")

                try:
                    if lastmod_datetime >= update_since_datetime:
                        filter_condition = Filter(
                            must=[
                                FieldCondition(key="url", match=MatchValue(value=loc))
                            ]
                        )
                        result = qdrant_client.scroll(
                            collection_name=COLLECTION_NAME,
                            limit=1,
                            scroll_filter=filter_condition,
                        )
                        # Om Den finns i databas
                        if result[0]:
                            datapoint = result[0][0]
                            update_date_str = datapoint.payload.get("update_date")
                            # Om datum finns i databas
                            if update_date_str is not None:
                                try:
                                    update_date = datetime.strptime(  ## Senaste sätt som det sparas i databas
                                        update_date_str, "%Y-%m-%dT%H:%M:%S"
                                    )
                                    print("Första formatet")
                                except:
                                    try:
                                        update_date = datetime.strptime(  ## Gammalt sätt som det sparades i databas
                                            update_date_str, "%Y-%m-%d"
                                        )
                                        print("Andra formatet")
                                    except:
                                        update_date = datetime.strptime(  ## Format för att yttligare säkra. Lastmod format.
                                            update_date_str, "%Y-%m-%dT%H:%M:%SZ"
                                        )
                                        print("Tredje formatet")

                                print(
                                    f"Update_date är {update_date} och Last Modified-date är {lastmod_datetime}"
                                )
                                # Lägg till då det är en ändring efter förra uppladdningen
                                if update_date < lastmod_datetime:
                                    print("Hittade sida vid behov av uppdatering.")
                                    update_urls.append(
                                        {
                                            "url": loc,
                                            "lastmod": lastmod,
                                        }
                                    )
                                    continue
                            # Lägg till då den finns i databas men utan datum
                            else:
                                print("Hittade ingen datum men existerar")
                                urls_no_update_date.append(
                                    {
                                        "url": loc,
                                        "lastmod": lastmod,
                                    }
                                )
                                continue

                        # Sidan finns inte i databasen
                        else:
                            print("Finns ingen sida i databasen med denna url.")
                            new_urls.append(
                                {
                                    "url": loc,
                                    "lastmod": lastmod,
                                }
                            )
                            continue

                except ValueError as e:
                    print(f"Felaktigt datumformat i update_date {update_date}: {e}")
            # Finns ingen Datum i Sitemap
            else:
                print("Ingen lastmod i sitemap")
                urls_no_lastmod.append({"url": loc})
                continue

        # Options Vad man vill uppdatera/Lägga till i qdrant databasen
        add_urls(
            urls,
            new_urls,
            "Sidor som inte finns med i databasen hittades. Vill du lägga till dessa också?",
        )
        add_urls(
            urls,
            update_urls,
            " Existerande sidor med ändringar hittades, vill du uppdatera dessa?",
        )
        add_urls(
            urls,
            urls_no_update_date,
            "Hittade sida i databas men ingen datum i databasen. Vill du lägga till dessa?",
        )
        add_urls(
            urls,
            urls_no_lastmod,
            "Sidor utan lastmod(i sitemap) hittades. Vill du lägga till dessa också?",
        )

        # Uppdatera tillagda.
        if urls:
            print(
                "Uppdaterar efter",
                update_since,
                ", finns",
                len(urls),
                "stycken uppdaterade sidor.",
            )
            are_u_sure = input("Är du säker på att starta uppdateringen, (y/n)")
            if urls and are_u_sure.lower() == "y":
                total_update_sek = 0
                for url in urls:
                    # Kör update
                    total_update_sek += update_url_qdrant(url["url"])

                logging.basicConfig(
                    filename="../data/update_logg.txt",
                    level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s",
                )
                logging.info(f"Total Kostnad för uppdateringar:, {total_update_sek}SEK")


def add_urls(urls, new_list, message):
    if new_list:
        print("---------------------------------")
        for url in new_list:
            print(url["url"])
        print("Nuvarande totala urls:", len(urls))
        print("Dessa urls:", len(new_list))
        apply_new_urls = input(f"{len(new_list)} {message}(y/n)")
        if apply_new_urls.lower() == "y":
            urls += new_list


## Main Execution

# Setup
load_dotenv(dotenv_path="../data/API_KEYS.env")
qdrant_api_key = os.getenv("QDRANT_API_KEY")

qdrant_client = QdrantClient(
    url=QDRANT_URL, port=QDRANT_PORT, https=True, api_key=qdrant_api_key
)

# Functionality
update_date = input(
    "Skriv datum du vill artiklar som ändrats efter ska uppdateras.(´YYYY-MM-DD´)"
)
update_qdrant_since(update_date)
