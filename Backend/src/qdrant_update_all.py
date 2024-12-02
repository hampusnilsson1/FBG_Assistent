import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from dateutil import parser

# Funktion hämtas från fil
import individual_scrap_update_qdrant
from individual_scrap_update_qdrant import update_url_qdrant


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
        urls_no_lastmod = []
        for url in root.findall("ns:url", namespace):
            loc = url.find("ns:loc", namespace).text
            lastmod_elem = url.find("ns:lastmod", namespace)
            if lastmod_elem is not None and lastmod_elem.text is not None:
                lastmod = lastmod_elem.text
                try:
                    lastmod_datetime = datetime.strptime(lastmod, "%Y-%m-%dT%H:%M:%SZ")
                    if lastmod_datetime >= update_since_datetime:
                        urls.append(
                            {
                                "url": loc,
                                "lastmod": lastmod,
                            }
                        )
                except ValueError as e:
                    print(f"Felaktigt datumformat i lastmod {lastmod}: {e}")
            else:
                #print(f"Ingen lastmod hittad för URL {loc}, uppdaterar/lägger till denna ändå.")
                urls_no_lastmod.append(
                    {
                        "url": loc,
                        #"lastmod": lastmod,
                    }
                )
        if urls_no_lastmod:
            print("Start",len(urls))
            print("Start nomod",len(urls_no_lastmod))
            apply_no_lastmod = input(f"{len(urls_no_lastmod)} Sidor utan lastmod hittades. Vill du lägga till dessa också? (y/n)")
            if apply_no_lastmod.lower() == "y":
                urls += urls_no_lastmod
        
        print("Försöker uppdatera från",update_since,"finns",len(urls),"stycken uppdaterade sidor")
        are_u_sure = input("Är du säker på att starta uppdateringen, (y/n)")
        if urls and are_u_sure.lower() == "y":
            total_update_sek = 0
            for url in urls:
                total_update_sek += update_url_qdrant(url["url"])
            individual_scrap_update_qdrant.setupLogging("../data/Price_logg.txt")
            individual_scrap_update_qdrant.logging(f"Total Kostnad för uppdateringar:",total_update_sek,"SEK")

individual_scrap_update_qdrant
update_date = input("Skriv datum du vill artiklar som ändrats efter ska uppdateras.(´YYYY-MM-DD´)")        
update_qdrant_since(update_date)
