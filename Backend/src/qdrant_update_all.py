import requests
import os
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models
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


def get_evolution_pdf_update(sitemap_url, remove_nonexist=False):
    # Hämta alla evolution pdfer i databasen
    qdrant_filter = models.Filter(
        must=[
            models.FieldCondition(key="url", match=models.MatchText(text="evolution"))
        ]
    )

    obj_qdrant_pdfs, next_page_offset = qdrant_client.scroll(
        collection_name=COLLECTION_NAME,
        limit=100,
        scroll_filter=qdrant_filter,
    )

    while next_page_offset is not None:
        new_points, next_page_offset = qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=qdrant_filter,
            limit=100,
            offset=next_page_offset,
        )
        obj_qdrant_pdfs.extend(new_points)

    qdrant_pdfs = []
    if obj_qdrant_pdfs[0]:
        for pdf in obj_qdrant_pdfs:
            url = pdf.payload.get("url")
            version = pdf.payload.get("version")
            if not version:
                version = "0.1"
            qdrant_pdfs.append({"url": url, "version": version})

    # Hämta alla existerande evolution pdfer i sitemap
    response = requests.get(sitemap_url)

    if response.status_code == 200:
        data = response.json()

        evolution_pdfs = []
        for item in data["data"]:
            version = item["version"]
            url = item["url"]
            title = item["name"]
            if version and url:
                evolution_pdfs.append({"url": url, "version": version, "title": title})

        qdrant_evolution_urls = set(pdf["url"] for pdf in qdrant_pdfs)
        sitemap_evolution_urls = set(pdf["url"] for pdf in evolution_pdfs)

        # Find URLs to remove
        if remove_nonexist == True:
            urls_to_remove = qdrant_evolution_urls - sitemap_evolution_urls
            logging.info(
                f"Tar bort {len(urls_to_remove)} stycken gamla evolution pdfer."
            )
            # TA BORT ALLA EVOLUTION PDFER SOM INTE LÄNGRE FINNS I SITEMAP?
            qdrant_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="url", match=models.MatchAny(any=urls_to_remove)
                    ),
                ]
            )

            points_selector = models.FilterSelector(filter=qdrant_filter)

            qdrant_client.delete(
                collection_name=COLLECTION_NAME, points_selector=points_selector
            )

        # Uppdatera om de finns annan version
        for ev_pdf in evolution_pdfs:
            if not ev_pdf["url"].endswith(".pdf"):
                print("Not a PDF")
                continue
            
            matching_qdrant = next(
                (
                    qdrant_pdf
                    for qdrant_pdf in qdrant_pdfs
                    if ev_pdf["url"] == qdrant_pdf["url"]
                ), None
            )
            if matching_qdrant is None:
                print("None Värde på qdrant ")
                continue
            if (
                any(ev_pdf["url"] == qdrant_pdf["url"] for qdrant_pdf in qdrant_pdfs)
                and ev_pdf["version"] != matching_qdrant["version"] and ev_pdf["version"] != "0.1"
            ):
                print("matching_qdrant",matching_qdrant["version"])
                print("matching_qdrant",type(matching_qdrant["version"]))
                print("Update")
                print("ev_pdf",ev_pdf["version"])
                print("ev_pdf",type(ev_pdf["version"]))
                # Ta bort gammal
                remove_url_qdrant(ev_pdf["url"])
                # Uppdatera till den nya
                update_url_qdrant(
                    ev_pdf["url"], evolution_pdf=True, pdf_title=ev_pdf["title"],pdf_version=ev_pdf["version"]
                )
            elif matching_qdrant is None:
                # Lägg till ny datapunkt
                print("New")
                update_url_qdrant(
                    ev_pdf["url"], evolution_pdf=True, pdf_title=ev_pdf["title"],pdf_version=ev_pdf["version"]
                )
            else:
                print("Ingen uppdatering behövs")


def remove_url_qdrant(url):
    qdrant_filter = models.Filter(
        must=[models.FieldCondition(key="url", match=models.MatchValue(value=url))]
    )

    point_selector = models.FilterSelector(filter=qdrant_filter)

    qdrant_client.delete(
        collection_name=COLLECTION_NAME, points_selector=point_selector
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
                                except:
                                    try:
                                        update_date = datetime.strptime(  ## Gammalt sätt som det sparades i databas
                                            update_date_str, "%Y-%m-%d"
                                        )
                                    except:
                                        update_date = datetime.strptime(  ## Format för att yttligare säkra. Lastmod format.
                                            update_date_str, "%Y-%m-%dT%H:%M:%SZ"
                                        )

                                logging.info(
                                    f"Update_date är {update_date} och Last Modified-date är {lastmod_datetime}"
                                )
                                # Lägg till då det är en ändring efter förra uppladdningen
                                if update_date < lastmod_datetime:
                                    logging.info(
                                        "Hittade sida vid behov av uppdatering."
                                    )
                                    update_urls.append(
                                        {
                                            "url": loc,
                                            "lastmod": lastmod,
                                        }
                                    )
                                    continue
                            # Lägg till då den finns i databas men utan datum
                            else:
                                logging.info("Hittade ingen datum men existerar")
                                urls_no_update_date.append(
                                    {
                                        "url": loc,
                                        "lastmod": lastmod,
                                    }
                                )
                                continue

                        # Sidan finns inte i databasen
                        else:
                            logging.info("Finns ingen sida i databasen med denna url.")
                            new_urls.append(
                                {
                                    "url": loc,
                                    "lastmod": lastmod,
                                }
                            )
                            continue

                except ValueError as e:
                    logging.info(
                        f"Felaktigt datumformat i update_date {update_date}: {e}"
                    )
            # Finns ingen Datum i Sitemap
            else:
                logging.info("Ingen lastmod med denna url i sitemap")
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
                ",",
                len(urls),
                "stycken sidor markerade för uppdatering.",
            )
            are_u_sure = input("Är du säker på att starta uppdateringen, (y/n)")
            if urls and are_u_sure.lower() == "y":
                total_update_sek = 0
                url_count = 0
                for url in urls:
                    url_count += 1
                    logging.info(f"Just nu på url nr: {url_count} av {len(urls)}")
                    # Kör update
                    total_update_sek += update_url_qdrant(url["url"])

                logging.basicConfig(
                    filename="../data/update_logg.txt",
                    level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s",
                )
                logging.info(f"Total Kostnad för uppdateringar: {total_update_sek}SEK")


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

#Används endast för att rensa de gamla sättet att spara Evolution pdferna(Genom att ta bort kolumnen source_url på dessa datapunkter)
def clear_source_url_evolution():    
    filter_condition = models.Filter(
        must=[
            models.FieldCondition(
                key="url",
                match=models.MatchText(text="evolution")
            )
        ]
    )

    # Kör clear_payload för att ta bort 'source_url' från alla matchande punkter
    response = qdrant_client.delete_payload(
        collection_name=COLLECTION_NAME,
        keys=["source_url"],
        points=models.FilterSelector(filter=filter_condition)
    )
    print(response)


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
if update_date:
    update_qdrant_since(update_date)

evolution_update = input("Vill du uppdatera alla Evolution Pdfer?.(y/n)")

if evolution_update.lower() == "y":
    remove_old_str = input(
        "Vill du ta bort alla gamla Evolution Pdfer samtidigt?.(y/n)"
    )
    remove_old = False
    if remove_old_str.lower() == "y":
        remove_old = True

    get_evolution_pdf_update(
        "https://intranet.falkenberg.se/fbg_apps/services/evolution/documents.php",
        remove_nonexist=remove_old,
    )