import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# Funktion hämtas från fil
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
        for url in root.findall("ns:url", namespace):
            loc = url.find("ns:loc", namespace).text
            lastmod = (
                url.find("ns:lastmod", namespace).text
                if url.find("ns:lastmod", namespace) is not None
                else None
            )
            lastmod_datetime = datetime.strptime(lastmod, "%Y-%m-%dT%H:%M:%SZ")
            if lastmod_datetime >= update_since_datetime:
                # Append parsed data as a dictionary
                urls.append(
                    {
                        "url": loc,
                        "lastmod": lastmod,
                    }
                )

        if urls:
            for url in urls:
                update_url_qdrant(url["url"])
