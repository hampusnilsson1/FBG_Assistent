import requests
import os
import re
import json
import threading
import queue
from dotenv import load_dotenv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from flask_limiter import Limiter
from asgiref.wsgi import WsgiToAsgi

from qdrant_client import QdrantClient

import stanza
import warnings

import model_config
from llm_client import get_client

api_keys_path = "../data/API_KEYS.env"
STANZA_MODEL_PATH = "../data/stanza_resources"


def load_api_key(key_variable):
    if not os.path.exists(api_keys_path):
        raise FileNotFoundError(f"{api_keys_path} file not found.")
    load_dotenv(dotenv_path=api_keys_path)
    api_key = os.getenv(key_variable)
    if not api_key is None:
        return api_key

    raise ValueError(
        "API key was not found!, Make sure the environment variable is set."
    )


# Qdrant
collection_name = "FalkenbergsKommunsHemsida_RAG"
qdrant_api_key = load_api_key("QDRANT_API_KEY")
qdrant_url = "https://qdrant.utvecklingfalkenberg.se"
qdrant_client = QdrantClient(
    url=qdrant_url, port=443, https=True, api_key=qdrant_api_key
)

if not qdrant_client.collection_exists(collection_name):
    print(f"Varning: Qdrant-collection '{collection_name}' saknas!")

# LLM Client (provider-agnostic)
api_keys = {
    "openai": load_api_key("OPENAI_API_KEY"),
    "google": load_api_key("GOOGLE_API_KEY"),
}
llm = get_client(api_keys, qdrant_client, collection_name)

# Directus Chat Databas
chat_api_url = "https://nav.utvecklingfalkenberg.se/items/falkenberg_kommun_chat"

# Directus Message Databas
message_api_url = "https://nav.utvecklingfalkenberg.se/items/falkenberg_kommun_messages"

headers = {"Content-Type": "application/json"}
params = {"access_token": load_api_key("DIRECTUS_KEY")}


def directus_get_cost(chat_id):
    cost_params = {
        "access_token": load_api_key("DIRECTUS_KEY"),
        "filter[chat_id][_eq]": chat_id,
        "fields": "cost_usd",
    }
    response = requests.get(chat_api_url, headers=headers, params=cost_params)

    if response.status_code == 200:
        data = response.json().get("data")
        if data:
            cost_usd = data[0]["cost_usd"]
            if cost_usd is None:
                cost_usd = 0.0

            return cost_usd
        else:
            print("No data found for the given chat_id")
            return None
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None


# Remove emojis from answer right before saving in database
def remove_emojis(text):
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F"  # Smiley
        "\U0001F300-\U0001F5FF"  # Symbols & Pictographs
        "\U0001F680-\U0001F6FF"  # Transport & Map
        "\U0001F700-\U0001F77F"  # Alchemical Symbols
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U00002600-\U000027BF"  # Miscellaneous Symbols
        "\U0001F1E0-\U0001F1FF"  # Flags (iOS)
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub(r"", text)


# Ladda ner och initiera svenska modellen, ignorera orelevanta varningar.
warnings.filterwarnings("ignore", category=FutureWarning)
if not os.path.exists(
    f"{STANZA_MODEL_PATH}/sv"
):
    stanza.download("sv", model_dir=STANZA_MODEL_PATH)

nlp = stanza.Pipeline("sv", model_dir=STANZA_MODEL_PATH)


def check_personal_info(text, contain=False):
    result = text
    # Telefonnummer
    result = re.sub(r"\b(\+46|0)[\s\-]?7[\d\s\-]{8}\b", "[REDACTED PHONE_NUM]", text)

    # Personnummer
    result = re.sub(r"\b(\d{6}|\d{8})[-+ ]?\d{4}\b", "[REDACTED PER_NUM]", text)

    doc = nlp(result)
    for ent in doc.entities:
        if ent.type in ["PER"]:
            result = result.replace(ent.text, f"[REDACTED {ent.type}]")
    print(result)
    # If contain = True then return if found or not
    if contain == True:
        if result != text:
            return True
        else:
            return False

    # If not contain then return the new text
    return result


# ============================================================
# SYSTEM PROMPT
# ============================================================

def build_system_prompt(user_input):
    """Build the system prompt for the Falkis assistant."""
    utc_time = datetime.now(timezone.utc).replace(microsecond=0)
    current_date_time = utc_time.astimezone(ZoneInfo("Europe/Stockholm"))
    current_date_time_str = current_date_time.strftime("%Y-%m-%dT%H:%M:%S")

    # Build domain descriptions for the prompt
    domain_descriptions = "\n".join(
        f"      - **{domain}**: {desc}"
        for domain, desc in model_config.ALLOWED_DOMAINS_INFO.items()
    )

    return f"""Ditt namn är Falkis. Du är en professionell, gullig och hjälpsam falk-assistent som ENBART svarar på frågor relaterade till Falkenbergs kommun och de tillhandahållna dokumenten.

    SÄKERHETSREGLER:
    - Du får under inga omständigheter använda nedsättande, rasistiskt, kränkande eller hatiskt språk.
    - Om användaren ställer frågor som är stötande, ska du artigt svara att du endast är här för att hjälpa till med frågor om Falkenbergs kommun.
    - Om du är 100% säker på att frågan saknar koppling till Falkenbergs kommun (t.ex. allmänna fakta om rymden, utländska kändisar), ska du svara: 
    "Jag är Falkis och jag hjälper bara till med frågor om Falkenbergs kommun. Kan jag hjälpa dig med något som rör vår kommun istället?"
    - VIKTIGT: Namn på personer (t.ex. lokalpolitiker som Per Svensson), projekt (t.ex. Agenda 2030) eller frågor om vem du är ("Vem är du/Falkis?") ÄR relaterade till ditt uppdrag. Om du är osäker på om ett namn/ämne rör kommunen: ANVÄND DINA SÖKVERKTYG FÖRST innan du avvisar frågan!

    VERKTYG:
    Du har tillgång till två sökverktyg:
    1. **search_knowledge_base** — Sök i Falkenbergs kommuns kunskapsbas (indexerade dokument, PDF:er och webbsidor från kommun.falkenberg.se). Använd detta för detaljerad kommunal information som regler, kontaktuppgifter och officiella dokument.
    2. **web_search** — Sök på webben (begränsat till specifika domäner). Använd detta för aktuell/uppdaterad information som kanske inte finns i kunskapsbasen.

    WEBBSÖKNINGENS DOMÄNER OCH INNEHÅLL:
{domain_descriptions}

    INSTRUKTIONER FÖR SVAR:
    1. Använd dina sökverktyg för att hitta relevant information innan du svarar på faktafrågor.
    2. Välj rätt verktyg baserat på frågan: t.ex. frågor om lägenheter/hyra → web_search (fabo.se), frågor om sopor/vatten → web_search (vivab.se), frågor om restauranger/evenemang → web_search (falkenberg.se), frågor om kommunala tjänster → search_knowledge_base.
    3. Om svaret inte hittas via verktygen, säg att du inte hittar informationen men hänvisa gärna till kontaktcenter tel:0346-88 60 00 / mail:kontaktcenter@falkenberg.se
    4. Svara på samma språk som användaren skriver på ({user_input}).
    5. Dagens datum och tid är {current_date_time_str}.
    6. För enkla hälsningar och uppföljningsfrågor som inte kräver ny information, svara direkt utan att använda verktyg.
    
    KÄLLHANTERING:
    - Varje faktapåstående ska ha en klickbar länk till exakt källa.
    - Använd beskrivande text i länken, t.ex. [Falkenbergs kommuns bygglovssida](https://...)
      eller [FABO - Betala hyra](https://fabo.se/hyresinformation/...).
    - Ange aldrig bara domännamn som (https://fabo.se) — länka alltid till den specifika
      undersidan där informationen finns.
    - Ange aldrig fotnotsnummer som [1] eller [3] — de ska alltid ersättas med beskrivande länkar.
    - Använd rena URL:er utan spårningsparametrar (?utm_source=...).
    """


# ============================================================
# MAIN LOGIC — Agentic RAG
# ============================================================

def get_result(user_input, user_history, chat_id, MAX_INPUT_CHAR):
    """
    Run the agentic RAG loop.
    The LLM decides whether to search the knowledge base,
    search the web, or answer directly.
    """

    # Build system prompt
    system_prompt = build_system_prompt(user_input)

    # Build messages list (history + current question)
    messages = []
    for message in user_history:
        role = message.get("role")
        content = message.get("content")
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_input})

    # Create or retrieve chat session in Directus
    if not chat_id or not user_history:
        print("Hittade inte chat_id eller user_history så skapas ny chatt", chat_id)
        chat_data = {}
        post_response = requests.post(
            chat_api_url, json=chat_data, headers=headers, params=params
        )
        if post_response.status_code != 200:
            print("Fel vid skapande av ny chatt.")
            print("Chat creation response:", post_response.json())
            chat_id = None
        else:
            print("Chat creation response:", post_response.json())
            chat_id = post_response.json().get("data", {}).get("chat_id")
            print("Skapat nytt id: ", chat_id)

    # Use a thread-safe queue for real-time streaming
    chunk_queue = queue.Queue()
    _SENTINEL = object()  # Signals that the agent is done
    agent_result = {}

    def _run_agent():
        """Run agent in background thread, push chunks to queue."""
        def stream_callback(text_chunk):
            chunk_queue.put(text_chunk)

        result = llm.run_agent(messages, system_prompt, stream_callback)
        agent_result.update(result)
        chunk_queue.put(_SENTINEL)

    def generate():
        # Send chat_id to frontend first
        yield json.dumps({"chat_id": chat_id}) + "\n<END_OF_JSON>\n"

        # Start the agent in a background thread
        agent_thread = threading.Thread(target=_run_agent, daemon=True)
        agent_thread.start()

        # Yield chunks in real-time as the agent streams them
        while True:
            chunk = chunk_queue.get()
            if chunk is _SENTINEL:
                break
            yield chunk

        # Wait for thread to fully finish
        agent_thread.join()

        # ---- Post-response: save to Directus ----
        full_response = agent_result.get("full_response", "")
        question_cost = agent_result.get("cost_usd", 0.0)

        full_response_no_emojis = remove_emojis(full_response)
        user_input_anonymized = check_personal_info(user_input)
        user_input_anonym_no_emoji = remove_emojis(user_input_anonymized)

        if chat_id:
            print("Använder: ", chat_id)
            message_data = {
                "chat_id": chat_id,
                "prompt": user_input_anonym_no_emoji,
                "response": full_response_no_emojis,
            }
            message_response = requests.post(
                message_api_url, json=message_data, headers=headers, params=params
            )

            if message_response.status_code != 200:
                print(
                    "Fel vid skickande av svaret i API:n. Hela request: ",
                    message_api_url,
                    message_data,
                    headers,
                    params,
                )

            # Hämta nuvarande kostnad för chatt
            update_chat_api_url = f"{chat_api_url}/{chat_id}"

            total_chat_cost = directus_get_cost(chat_id)
            total_chat_cost += question_cost

            cost_data = {"cost_usd": total_chat_cost}

            chat_cost_params = params.copy()
            chat_cost_params["filter[chat_id][_eq]"] = chat_id

            # Uppdatera chat och lägg till frågans kostnad
            try:
                response = requests.patch(
                    update_chat_api_url,
                    json=cost_data,
                    headers=headers,
                    params=chat_cost_params,
                )

                if response.status_code == 200:
                    print(f"Directus cost_usd uppdaterad! ID: {chat_id}, Cost: ${question_cost:.6f}")
                else:
                    print(f"Fel vid uppdatering av kostnad: {response.text}")
            except requests.exceptions.RequestException as e:
                print(f"Nätverksfel vid kostnadsuppdatering: {str(e)}")

    return generate


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)
CORS(app)
# Begränsar antalet requests
limiter = Limiter(app=app, key_func=lambda: "global", storage_uri="memory://")

asgi_app = WsgiToAsgi(app)


# Kontroll av user_input
@app.route("/check_pii", methods=["POST"])
def check_pii():
    data = request.get_json()
    if not data or "user_input" not in data:
        return jsonify({"error": "Ingen användarinput inmatad"}), 400

    user_input = str(data["user_input"])
    print("Input:", user_input)
    pii_detected = check_personal_info(user_input, contain=True)
    print("Detected?:", pii_detected)
    return jsonify({"pii_detected": pii_detected}), 200


@app.route("/generate", methods=["POST"])
@limiter.limit("100 per hour")
def generate():
    data = request.get_json()
    if not data or "user_input" not in data:
        return jsonify({"error": "Ingen användarinput inmatad"}), 400

    user_input = data["user_input"]

    if "user_history" in data and "chat_id" in data and data["chat_id"] != "":
        history_list = data["user_history"]
        if len(history_list) > 12:
            # Begränsa till de senaste 12 objekten, 6 "frågor"
            user_history = history_list[-12:]
        else:
            user_history = history_list

        chat_id = data["chat_id"]

        generator = get_result(user_input, user_history, chat_id, 1000)
    else:
        generator = get_result(user_input, [], None, 1000)
    response = Response(stream_with_context(generator()), mimetype="text/plain")
    return response


@app.route("/feedback", methods=["POST"])
def send_feedback():
    data = request.get_json()
    required_fields = {
        "chat_id",
        "user_rating",
    }
    if not data or not required_fields.issubset(data.keys()):
        print("Alla parametrar finns inte med")
        return jsonify({"error": "Ingen feedback inmatad/Fel Format"}), 400

    # Validerar user_rating
    if "user_rating" in data:
        try:
            user_rating = int(data["user_rating"])
            if user_rating < 1 or user_rating > 5:
                return (
                    jsonify({"error": "Betyget måste vara ett heltal mellan 1 och 5"}),
                    400,
                )
        except ValueError:
            return (
                jsonify({"error": "Betyget måste vara ett heltal mellan 1 och 5"}),
                400,
            )

    # Förbered data för att skicka till Directus API
    chat_id = data["chat_id"]
    del data["chat_id"]

    update_chat_api_url = f"{chat_api_url}/{chat_id}"

    # Säkrar att Idt finns
    response = requests.get(update_chat_api_url, headers=headers, params=params)
    if response.status_code != 200:
        return jsonify({"error": "Id existerar inte!"}), 400

    # Uppdatera Betyg i databas
    try:
        response = requests.patch(
            update_chat_api_url, json=data, headers=headers, params=params
        )

        if response.status_code == 200:
            print("Directus Feedback uppdaterad!ID:", chat_id)
            return jsonify({"message": "Tack för din feedback!"}), 200
        else:
            return (
                jsonify({"error": f"Fel vid uppdatering av feedback: {response.text}"}),
                response.status_code,
            )
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Nätverksfel: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=3003)
