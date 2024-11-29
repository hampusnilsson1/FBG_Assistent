import requests
import os
import re
import json
import tiktoken
from dotenv import load_dotenv
from datetime import datetime

import openai
from qdrant_client import QdrantClient

from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from flask_limiter import Limiter
from asgiref.wsgi import WsgiToAsgi

import stanza
import warnings

api_keys_path = "../data/API_KEYS.env"
STANZA_MODEL_PATH = "../data/stanza_resources"  # Eventuellt ändra denna för docker


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
collection_name = "FalkenbergsKommunsHemsida"
qdrant_api_key = load_api_key("QDRANT_API_KEY")
qdrant_url = "https://qdrant.utvecklingfalkenberg.se"
qdrant_client = QdrantClient(
    url=qdrant_url, port=443, https=True, api_key=qdrant_api_key
)

# OpenAI
openai.api_key = load_api_key("OPENAI_API_KEY")
GPT_MODEL = "gpt-4o"

# Directus Chat Databas
chat_api_url = "https://nav.utvecklingfalkenberg.se/items/falkenberg_kommun_chat"

# Directus Message Databas
message_api_url = "https://nav.utvecklingfalkenberg.se/items/falkenberg_kommun_messages"

headers = {"Content-Type": "application/json"}
params = {"access_token": load_api_key("DIRECTUS_KEY")}


def generate_embeddings(text):  # Gör om till "sökkordinat"
    response = openai.Embedding.create(input=text, model="text-embedding-3-large")
    return response["data"][0]["embedding"]


def search_collection(
    qdrant_client, collection_name, user_query_embedding
):  # Söker efter närmsta 10 i kordinat systemet
    response = qdrant_client.search(
        collection_name=collection_name,
        query_vector=user_query_embedding,
        limit=10,
        with_payload=True,
    )
    return response


# OpenAI Token Counter
def count_tokens(text, model="gpt-4o"):

    encoding = tiktoken.encoding_for_model(model)

    tokens = encoding.encode(text)
    num_tokens = len(tokens)
    return num_tokens


# Token Cost Calculator
def calculate_cost(text, model="gpt-4o", is_input=True):
    # Hämta antalet tokens
    num_tokens = count_tokens(text, model)

    # Kostnadsberäkningar per 1000 tokens
    if model == "gpt-4o":
        if is_input:
            cost_per_1000_tokens = 0.0025  # USD
        else:  # Output
            cost_per_1000_tokens = 0.0100  # USD
    elif model == "text-embedding-3-large":
        cost_per_1000_tokens = 0.00013  # USD
    else:
        raise ValueError("Unsupported model")

    # Beräkna kostnaden
    cost = (num_tokens / 1000) * cost_per_1000_tokens
    return cost


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
):  # Osäker på var denna sparar i docker?
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


# Start
def get_result(
    user_input, user_history, chat_id, MAX_INPUT_CHAR
):
    question_cost = 0
    # Loopa igenom user_historys alla frågor.
    user_input_combo = ""
    for message in user_history:
        role = message.get("role")
        if role == "user":
            content = message.get("content")
            user_input_combo += "," + str(content)
    user_input_combo = user_input_combo[:MAX_INPUT_CHAR]

    # Här ska GPT generera en relevant fråga som vi kan söka efter information i QDRANT
    # Med user_input som den senaste fråga och user_input combo som frågornas historik.
    query_instruction = f"""Du ska generera en kort, koncis och relevant fråga baserat på användarens senaste fråga och eventuellt tidigare frågor om FBG kommun.

        Tidigare frågor: "{user_input_combo}" (första frågan i konversationen först).

        Generera en fråga som:
        1. Fokuserar på användarens senaste fråga, men tar hänsyn till tidigare frågor om de är relevanta.
        2. Om tidigare frågor är relevanta, inkludera endast då deras kontext i den nya frågan; annars fokusera enbart på den senaste frågan.
        3. Frågan ska vara optimerad för att söka information i en inbäddad databas.
        
    """
    query_input = [
        {"role": "system", "content": query_instruction},
        {"role": "user", "content": user_input},
    ]

    openai_query = openai.ChatCompletion.create(model=GPT_MODEL, messages=query_input)
    question_cost += calculate_cost(json.dumps(query_input))

    query_text_out = openai_query["choices"][0]["message"]["content"]
    question_cost += calculate_cost(query_text_out, is_input=False)

    user_embedding = generate_embeddings(query_text_out)
    question_cost += calculate_cost(query_text_out, "text-embedding-3-large")

    search_results = search_collection(qdrant_client, collection_name, user_embedding)
    similar_texts = [
        {
            "chunk": result.payload["chunk"],
            "title": result.payload["title"],
            "url": result.payload["url"],
            "score": result.score,
            "id": result.id,
        }
        for result in search_results
    ]
    #Send in current datetime so it knows
    current_date_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    # Prepare the prompt for GPT-4o in Swedish
    instructions_prompt = f"""
    Du är en hjälpsam assistent med namnet Falkis, du är en gullig liten falk-assistent som hjälper användaren att hitta information om Falkenbergs kommun. 

    Här är information som skulle kunna vara till hjälp för att hjälpa användaren kring frågan (datum och tid för denna förfrågan: {current_date_time}):
    Dokument:
    {similar_texts[0]['chunk']}
    URL: {similar_texts[0]['url']}
    Likhetsscore: {similar_texts[0]['score']}

    Dokument:
    {similar_texts[1]['chunk']}
    URL: {similar_texts[1]['url']}
    Likhetsscore: {similar_texts[1]['score']}
    Dokument:
    {similar_texts[2]['chunk']}
    URL: {similar_texts[2]['url']}
    Likhetsscore: {similar_texts[2]['score']}
        Dokument:
    {similar_texts[3]['chunk']}
    URL: {similar_texts[3]['url']}
    Likhetsscore: {similar_texts[3]['score']}
        Dokument:
    {similar_texts[4]['chunk']}
    URL: {similar_texts[4]['url']}
    Likhetsscore: {similar_texts[4]['score']}


    Hjälp användaren att få svar på sin fråga.
    Redovisa endast om dokumenten är relevant. 
    Om du använder dokument, hänvisa alltid med länk till källan
    Reply in the same language as: {user_input}.
    """
    sources = []
    for qdrant_text in similar_texts: # For future development?
        if qdrant_text["score"] >= 0.70 and qdrant_text["url"] not in [
            source["url"] for source in sources
        ]:
            sources.append(qdrant_text)

    print("Källor:")
    for source in sources:
        print(source["url"], source["score"])

    messages = [{"role": "system", "content": instructions_prompt}]
    for (
        message
    ) in (
        user_history
    ):  # Här eventuellt hämta med chat_id alla konversations chatter: https://nav.utvecklingfalkenberg.se/items/falkenberg_kommun_messages?access_token=XXXXXXCODE&filter[chat_id][_eq]=CHAT_IDDDD
        role = message.get("role")
        content = message.get("content")
        messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_input})
    question_cost += calculate_cost(json.dumps(messages))

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

    collected_response = []

    def generate():
        nonlocal question_cost

        yield json.dumps({"chat_id": chat_id, "sources": sources}) + "\n<END_OF_JSON>\n"

        # GPT-4o Generering
        completion = openai.ChatCompletion.create(
            model=GPT_MODEL,
            messages=messages,
            stream=True,
        )

        for chunk in completion:
            if chunk.choices[0].delta.get("content"):
                text_chunk = chunk.choices[0].delta["content"]
                collected_response.append(text_chunk)
                yield text_chunk

        # När hela text färdig uppdatera i databas.
        full_response = "".join(collected_response)
        question_cost += calculate_cost(full_response, "gpt-4o", is_input=False)
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

            chat_cost_params = params
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
                    print("Directus cost_usd uppdaterad!ID:", chat_id)
                    return jsonify({"message": "Konstnad Uppdaterad!"}), 200
                else:
                    return (
                        jsonify(
                            {
                                "error": f"Fel vid uppdatering av kostnad: {response.text}"
                            }
                        ),
                        response.status_code,
                    )
            except requests.exceptions.RequestException as e:
                return jsonify({"error": f"Nätverksfel: {str(e)}"}), 500

    return generate


app = Flask(__name__)
CORS(app)
# Begränasar antalet requests
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
    if not data or "user_input" not in data:  ## Här matas historiken in
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
    }  # Alternativ user_feedback också. Denna kan matas in men måste inte vara i fylld i nuläget.
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
