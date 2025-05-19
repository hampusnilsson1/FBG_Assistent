import os
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.http import models

import smtplib
from email.message import EmailMessage

# Ladda API-nyckel från .env-fil
load_dotenv(dotenv_path="/app/data/API_KEYS.env")
qdrant_api_key = os.getenv("QDRANT_API_KEY")

load_dotenv(dotenv_path="/app/data/EMAIL_INFO.env")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))

QDRANT_URL = "https://qdrant.utvecklingfalkenberg.se/"
QDRANT_PORT = 443
COLLECTION_NAME = "FalkenbergsKommunsHemsida"

qdrant_client = QdrantClient(
    url=QDRANT_URL, port=QDRANT_PORT, https=True, api_key=qdrant_api_key
)


## Web Sitemap Process Remove Diff
# Hämta alla punkter från Qdrant
def get_web_qdrant_urls():
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
                # Filter out empty URLs and PDF files
                if not url or "evolution" in url:
                    # print("Punkt saknar URL eller är en Evolution PDF. Hoppar över.")
                    continue
                # Filter out Linked Documents
                if source_url:
                    # print("Punkt är ett länkat dokument. Hoppar över.")
                    continue

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
def get_web_sitemap_urls(sitemap_url):
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


def remove_web_sitemap_url_diff(force=False):
    sitemap_url = (
        "https://kommun.falkenberg.se/index.php?option=com_jmap&view=sitemap&format=xml"
    )

    try:
        qdrant_urls = get_web_qdrant_urls()
        sitemap_urls = get_web_sitemap_urls(sitemap_url)

        # Hitta URL:er som finns i Qdrant men inte i sitemap
        missing_urls = qdrant_urls - sitemap_urls
        print(f"Totalt {len(missing_urls)} URL:er saknas i sitemap.")
        if missing_urls:
            if len(missing_urls) > 50 and not force:
                print(
                    "För många URL:er skiljer sig från sitemap, vänligen kontrollera."
                )
                send_alert_email(len(missing_urls), "Webb")
                return
            print("URL:er som finns i Qdrant men inte i sitemap:")
            for url in missing_urls:
                print(url)
            print("Tas bort från Qdrant...")
            remove_qdrant_urls(missing_urls)
        else:
            print("Alla Webb URL:er i Qdrant finns också i sitemap.")

    except Exception as e:
        print(f"Ett fel inträffade: {e}")


# Evolution Process Remove Diff
def get_evo_qdrant_urls():
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

    return qdrant_pdfs


def get_evo_sitemap_urls(sitemap_url):
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
        return evolution_pdfs


def remove_evo_sitemap_url_diff(force=False):
    qdrant_pdfs = get_evo_qdrant_urls()
    evolution_pdfs = get_evo_sitemap_urls(
        "https://intranet.falkenberg.se/fbg_apps/services/evolution/documents.php"
    )

    qdrant_evolution_urls = set(pdf["url"] for pdf in qdrant_pdfs)
    sitemap_evolution_urls = set(pdf["url"] for pdf in evolution_pdfs)

    # Find URLs to remove
    urls_to_remove = qdrant_evolution_urls - sitemap_evolution_urls
    if len(urls_to_remove) > 50 and not force:
        print(
            "För många evolution pdfer skiljer sig från sitemap, vänligen kontrollera."
        )  # Byt till True för att tvinga borttagning
        send_alert_email(len(urls_to_remove), "Evolution")
        return
    print(f"Tar bort {len(urls_to_remove)} stycken gamla evolution pdfer.")
    qdrant_filter = models.Filter(
        must=[
            models.FieldCondition(key="url", match=models.MatchAny(any=urls_to_remove)),
        ]
    )
    points_selector = models.FilterSelector(filter=qdrant_filter)
    qdrant_client.delete(
        collection_name=COLLECTION_NAME, points_selector=points_selector
    )


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


def send_alert_email(count, urltype="Webb"):
    msg = EmailMessage()
    msg.set_content(
        f"Antalet URL:er för {urltype} har överskridit 50 (nuvarande antal: {count}). Inga gamla datapunkter har raderats från Qdrant. Du måste hantera detta manuellt."
    )
    msg["Subject"] = "Varning: För många URL:er - Falkis Backend"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO

    try:
        with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASSWORD)
            smtp.send_message(msg)
            print("Mail skickat.")
    except Exception as e:
        print("Kunde inte skicka mail:", e)


# Huvudfunktion för att jämföra URL:er
def main():
    print("Tar bort gamla Webbsitemap URL:er...")
    remove_web_sitemap_url_diff(force=False)  # True för att tvinga borttagning
    print("Tar bort gamla Evolution URL:er...")
    remove_evo_sitemap_url_diff(force=False)  # True för att tvinga borttagning


if __name__ == "__main__":
    main()
