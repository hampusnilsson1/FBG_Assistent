from flask import Flask, request, jsonify
from asgiref.wsgi import WsgiToAsgi
from individual_scrap_update_qdrant import update_url_qdrant
from individual_remove_qdrant import remove_qdrant
from dotenv import load_dotenv
import os

app = Flask(__name__)
asgi_app = WsgiToAsgi(app)

# Load environment variables
load_dotenv(dotenv_path="/app/data/API_KEYS.env")
UPDATE_API_KEY = os.getenv("UPDATE_API_KEY")


@app.route("/update-qdrant", methods=["POST"])
def update_qdrant():
    try:
        data = request.get_json()
        if "api_key" not in data or data["api_key"] != UPDATE_API_KEY:
            return jsonify({"error": "Invalid or missing API key"}), 401
        if not data or "url" not in data:
            return jsonify({"error": "URL is required"}), 400

        url = data["url"]

        kwargs = {}
        if "title" in data:
            kwargs["providedTitle"] = data["title"]

        result = update_url_qdrant(url, **kwargs)

        return (
            jsonify(
                {
                    "message": "Successfully updated Qdrant",
                    "result": f"Cost: {result} SEK",
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/remove-qdrant", methods=["POST"])
def remove_qdrant_url():
    try:
        data = request.get_json()
        if "api_key" not in data or data["api_key"] != UPDATE_API_KEY:
            return jsonify({"error": "Invalid or missing API key"}), 401
        if not data or "url" not in data:
            return jsonify({"error": "URL is required"}), 400

        url = data["url"]
        response = remove_qdrant(url)

        return (
            jsonify(
                {
                    "message": "Successfully removed URL from Qdrant",
                    "result": str(response),
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500
