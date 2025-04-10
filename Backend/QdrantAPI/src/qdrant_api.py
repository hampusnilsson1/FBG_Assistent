from flask import Flask, request, jsonify
from asgiref.wsgi import WsgiToAsgi
from individual_scrap_update_qdrant import update_url_qdrant
from dotenv import load_dotenv
import os

app = Flask(__name__)
asgi_app = WsgiToAsgi(app)

# Load environment variables
load_dotenv(dotenv_path="../data/API_KEYS.env")
UPDATE_API_KEY = os.getenv("UPDATE_API_KEY")

@app.route('/update-qdrant', methods=['POST'])
def update_qdrant():
    try:
        data = request.get_json()
        if 'api_key' not in data or data['api_key'] != UPDATE_API_KEY:
            return jsonify({'error': 'Invalid or missing API key'}), 401
        if not data or 'url' not in data:
            return jsonify({'error': 'URL is required'}), 400

        #url = data['url']
        #result = update_url_qdrant(url)
        
        return jsonify({'message': 'Successfully updated Qdrant', 'result': "result"}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500