"""
Provider-agnostic LLM client wrapper.

Uses the OpenAI Responses API with:
  - Built-in web_search (domain-restricted)
  - Custom function tool for Qdrant knowledge base search

To add a new provider (e.g. Google), create a new class that
inherits from LLMClient and implement the abstract methods.
Then update model_config.PROVIDER and instantiate the new class
in get_client().
"""

import json
from abc import ABC, abstractmethod

import openai
from qdrant_client import QdrantClient, models as qdrant_models

import model_config


# ============================================================
# TOOL DEFINITIONS
# ============================================================

def build_tools():
    """Build the tools array for the Responses API."""
    return [
        # Built-in web search — locked to allowed domains
        {
            "type": "web_search",
            "filters": {
                "allowed_domains": model_config.ALLOWED_DOMAINS,
            },
        },
        # Custom Qdrant knowledge base search
        {
            "type": "function",
            "name": "search_knowledge_base",
            "description": (
                "Search Falkenberg municipality's internal knowledge base "
                "(indexed documents, PDFs, and web pages from kommun.falkenberg.se). "
                "Use this for detailed municipal information like regulations, "
                "contact details, services, events, and official documents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query in Swedish",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional specific keywords for filtering "
                            "(names of people, places, dates, addresses)"
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    ]


# ============================================================
# ABSTRACT BASE CLASS
# ============================================================

class LLMClient(ABC):
    """
    Abstract base class for LLM providers.
    Implement this for each provider you want to support.
    """

    @abstractmethod
    def run_agent(self, messages, system_prompt, stream_callback):
        """
        Run the agentic loop.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            system_prompt: System instructions string.
            stream_callback: Callable(text_chunk: str) for streaming.

        Returns:
            dict with keys:
                "full_response": str — complete response text
                "input_tokens": int
                "output_tokens": int
                "cost_usd": float
        """
        pass

    def calculate_cost(self, input_tokens, output_tokens, cached_tokens=0, model=None, input_price_per_m=None, output_price_per_m=None, cached_price_per_m=None):
        """
        Calculate cost in USD given token counts.
        Either use provided prices per million tokens, or look up the model in model_config.PRICING.
        """
        if input_price_per_m is not None and output_price_per_m is not None:
            if cached_price_per_m is None:
                cached_price_per_m = input_price_per_m
            uncached_tokens = max(0, input_tokens - cached_tokens)
            
            input_cost = (uncached_tokens / 1_000_000) * input_price_per_m
            cached_cost = (cached_tokens / 1_000_000) * cached_price_per_m
            output_cost = (output_tokens / 1_000_000) * output_price_per_m
            return input_cost + cached_cost + output_cost

        if model:
            pricing = getattr(model_config, "PRICING", {}).get(model, {})
            input_p = pricing.get("input", 0)
            cached_p = pricing.get("cached_input", input_p)
            output_p = pricing.get("output", 0)
            
            uncached_tokens = max(0, input_tokens - cached_tokens)
            input_cost = (uncached_tokens / 1_000_000) * input_p
            cached_cost = (cached_tokens / 1_000_000) * cached_p
            output_cost = (output_tokens / 1_000_000) * output_p
            return input_cost + cached_cost + output_cost
            
        return 0.0


class EmbeddingClient(ABC):
    """
    Abstract base class for Embedding providers.
    """

    @abstractmethod
    def create_embedding(self, text):
        """Create an embedding vector for the given text.

        Returns:
            list[float]
        """
        pass


# ============================================================
# OPENAI IMPLEMENTATION (Responses API)
# ============================================================

class OpenAIEmbeddingClient(EmbeddingClient):
    """OpenAI provider for embeddings."""

    def __init__(self, api_key):
        self.client = openai.OpenAI(api_key=api_key)

    def create_embedding(self, text):
        """Create embedding using OpenAI's embedding model."""
        response = self.client.embeddings.create(
            input=text,
            model=model_config.EMBEDDING_MODEL,
        )
        return response.data[0].embedding

class OpenAIClient(LLMClient):
    """OpenAI provider using the Responses API."""

    def __init__(self, api_key, qdrant_client, collection_name, embedding_client):
        self.client = openai.OpenAI(api_key=api_key)
        self.qdrant_client = qdrant_client
        self.collection_name = collection_name
        self.embedding_client = embedding_client
        self.tools = build_tools()

    # ---- Knowledge base search (called when agent uses the tool) ----

    def search_knowledge_base(self, query, keywords=None):
        """Execute a Qdrant knowledge base search."""
        # Generate embedding for the query using the injected embedding provider
        query_embedding = self.embedding_client.create_embedding(query)

        # Build keyword filter if keywords provided
        keyword_filter = None
        if keywords and len(keywords) > 0:
            keyword_filter = qdrant_models.Filter(
                should=[
                    qdrant_models.FieldCondition(
                        key="content",
                        match=qdrant_models.MatchText(text=kw),
                    )
                    for kw in keywords
                ]
            )

        # Search Qdrant
        if keyword_filter is None:
            results = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                limit=5,
                with_payload=True,
            ).points
        else:
            # Hybrid: vector search + keyword filter
            vector_results = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                limit=5,
                with_payload=True,
            ).points
            filtered_results, _ = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                scroll_filter=keyword_filter,
                limit=3,
            )
            filtered_ids = set(point.id for point in filtered_results)
            combined = list(filtered_results)
            for r in vector_results:
                if r.id not in filtered_ids:
                    combined.append(r)
                if len(combined) >= 5:
                    break
            results = combined[:5]

        # Format results for the agent
        documents = []
        for result in results:
            documents.append({
                "content": result.payload.get("content", ""),
                "title": result.payload.get("metadata", {}).get("title", ""),
                "url": result.payload.get("metadata", {}).get("url", ""),
                "score": getattr(result, "score", "keyword_match"),
            })

        return documents

    # ---- Agentic loop ----

    def run_agent(self, messages, system_prompt, stream_callback):
        """
        Run the agentic loop with the Responses API.

        Handles:
        - web_search_call: automatic (OpenAI handles it)
        - function_call (search_knowledge_base): we execute and feed back
        - text output: streamed via callback
        """
        total_input_tokens = 0
        total_cached_tokens = 0
        total_output_tokens = 0
        collected_text = []

        # Convert chat history to Responses API input format
        api_input = []
        for msg in messages:
            api_input.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        # Initial call with streaming
        stream = self.client.responses.create(
            model=model_config.CHAT_MODEL,
            instructions=system_prompt,
            input=api_input,
            tools=self.tools,
            stream=True,
        )

        # Track pending function calls
        current_call_id = None
        current_call_args = ""
        current_func_name = None

        for event in stream:
            # Text delta — stream to frontend
            if event.type == "response.output_text.delta":
                collected_text.append(event.delta)
                stream_callback(event.delta)

            # Function call arguments being built
            elif event.type == "response.function_call_arguments.delta":
                if current_call_id:
                    current_call_args += event.delta

            # A new output item (could be function_call or web_search_call)
            elif event.type == "response.output_item.added":
                if hasattr(event.item, "type"):
                    if event.item.type == "function_call":
                        current_call_id = getattr(event.item, "call_id", None)
                        current_func_name = getattr(event.item, "name", None)
                        current_call_args = ""

            # Function call arguments complete — execute our tool
            elif event.type == "response.function_call_arguments.done":
                call_id = current_call_id
                func_name = current_func_name
                args_str = current_call_args

                if func_name == "search_knowledge_base":
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {"query": args_str}

                    query = args.get("query", "")
                    keywords = args.get("keywords", [])

                    print(f"[Agent] Searching knowledge base: query='{query}', keywords={keywords}")
                    results = self.search_knowledge_base(query, keywords)

                    # Send results back to the agent and stream the final answer
                    followup_stream = self.client.responses.create(
                        model=model_config.CHAT_MODEL,
                        instructions=system_prompt,
                        input=api_input + [
                            {"type": "function_call", "call_id": call_id, "name": "search_knowledge_base", "arguments": args_str},
                            {"type": "function_call_output", "call_id": call_id, "output": json.dumps(results, ensure_ascii=False)},
                        ],
                        tools=self.tools,
                        stream=True,
                    )

                    for followup_event in followup_stream:
                        if followup_event.type == "response.output_text.delta":
                            collected_text.append(followup_event.delta)
                            stream_callback(followup_event.delta)
                        elif followup_event.type == "response.completed":
                            if hasattr(followup_event.response, "usage") and followup_event.response.usage:
                                total_input_tokens += getattr(followup_event.response.usage, "input_tokens", 0)
                                total_output_tokens += getattr(followup_event.response.usage, "output_tokens", 0)
                                
                                details = getattr(followup_event.response.usage, "prompt_tokens_details", None)
                                if details:
                                    total_cached_tokens += getattr(details, "cached_tokens", 0) if hasattr(details, "cached_tokens") else details.get("cached_tokens", 0)

                # Reset for next potential call
                current_call_id = None
                current_call_args = ""

            # Response completed — capture usage stats
            elif event.type == "response.completed":
                if hasattr(event.response, "usage") and event.response.usage:
                    total_input_tokens += getattr(event.response.usage, "input_tokens", 0)
                    total_output_tokens += getattr(event.response.usage, "output_tokens", 0)
                    
                    details = getattr(event.response.usage, "prompt_tokens_details", None)
                    if details:
                        total_cached_tokens += getattr(details, "cached_tokens", 0) if hasattr(details, "cached_tokens") else details.get("cached_tokens", 0)

        full_response = "".join(collected_text)
        cost_usd = self.calculate_cost(total_input_tokens, total_output_tokens, cached_tokens=total_cached_tokens, model=model_config.CHAT_MODEL)

        return {
            "full_response": full_response,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "cost_usd": cost_usd,
        }


# ============================================================
# GOOGLE IMPLEMENTATION (Future placeholder)
# ============================================================

# class GoogleClient(LLMClient):
#     """Google Gemini provider — implement when needed."""
#
#     def __init__(self, api_key, qdrant_client, collection_name):
#         # import google.generativeai as genai
#         # genai.configure(api_key=api_key)
#         pass
#
#     def run_agent(self, messages, system_prompt, stream_callback):
#         raise NotImplementedError("Google provider not yet implemented")
#
#     def create_embedding(self, text):
#         raise NotImplementedError("Google provider not yet implemented")
#
#     def calculate_cost(self, input_tokens, output_tokens, model=None):
#         raise NotImplementedError("Google provider not yet implemented")


# ============================================================
# FACTORY
# ============================================================

def get_embedding_client(api_keys):
    """Factory for embedding clients based on EMBEDDING_PROVIDER."""
    provider = getattr(model_config, "EMBEDDING_PROVIDER", "openai")
    
    if provider == "openai":
        return OpenAIEmbeddingClient(api_keys.get("openai"))
    else:
        raise ValueError(f"Unsupported embedding provider: {provider}")

def get_client(api_keys, qdrant_client, collection_name):
    """
    Factory function — returns the correct LLMClient based on
    the CHAT_PROVIDER setting in model_config.py.
    """
    embedding_client = get_embedding_client(api_keys)
    provider = getattr(model_config, "CHAT_PROVIDER", "openai")
    
    if provider == "openai":
        return OpenAIClient(api_keys.get("openai"), qdrant_client, collection_name, embedding_client)
    # elif provider == "google":
    #     return GoogleClient(api_keys.get("google"), qdrant_client, collection_name, embedding_client)
    else:
        raise ValueError(f"Unsupported chat provider: {provider}")
