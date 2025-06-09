# Falkis – AI Assistant for Falkenbergs Kommun

**Falkis** is an AI-powered assistant developed for the official website of [Falkenbergs Kommun](https://kommun.falkenberg.se/). It helps users find relevant and up-to-date information by answering questions directly on the site, enhancing user experience through intelligent search and conversational interaction.

---

## 🚀 Features

- 🤖 Intelligent question answering powered by vector search and OpenAI.
- 🔁 Backend system for updating and maintaining the knowledge base.
- 🧠 Context-aware responses using embeddings from relevant site content.
- 🌐 Frontend integration with Joomla modules using HTML, CSS, and JavaScript.
- 🔄 Automated CRON jobs for removing outdated information.

---

## 🏗️ Project Structure

### 🔙 Backend (Python)

- **API Server** – Handles incoming queries and generates AI responses.
- **Embedding Generator** – Processes and updates vector database from website content.
- **Utilities** – Scripts for scraping, preprocessing, and updating internal data.
- **CRON Jobs** – Scheduled tasks for maintaining data freshness.
- **Auto-Update** – Automatic syncing of vector database when website content changes.

> Technologies: Python, Flask, Qdrant Vector DB, OpenAI API

### 🌐 Frontend (HTML/CSS/JS)

- Integrated into Joomla via custom module.
- Dynamic chatbot interface styled with pure CSS.
- Minimal dependencies to ensure compatibility with Joomla.
- UIKit icons used for interface elements.

---

## 🧠 How It Works

1. **User types a question** in the Falkis chat window.
2. **Frontend sends request** to backend API.
3. **Backend searches** the vector database for relevant content.
4. **OpenAI generates a response** based on matched context.
5. **Answer is returned** to the user in the chat interface.
