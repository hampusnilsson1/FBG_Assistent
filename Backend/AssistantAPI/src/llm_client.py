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


def build_collections_description():
    """Build a human-readable description of available knowledge base collections."""
    desc = "Söker i Falkenbergs kommuns interna kunskapsbas (primär källa: kommun.falkenberg.se)."
    if model_config.SECONDARY_COLLECTIONS:
        desc += " Söker automatiskt även i följande specialiserade källor:\n"
        for coll_name, coll_desc in model_config.SECONDARY_COLLECTIONS.items():
            desc += f"  - **{coll_name}**: {coll_desc}\n"
    return desc


def build_tools():
    """Build the tools array for the Responses API."""
    tools = []

    # Built-in web search — only added if toggled on
    if model_config.WEB_SEARCH_ENABLED:
        tools.append(
            {
                "type": "web_search",
                "filters": {
                    "allowed_domains": model_config.ALLOWED_DOMAINS,
                },
            }
        )

    # Custom Qdrant knowledge base search (always available)
    tools.append(
        {
            "type": "function",
            "name": "search_knowledge_base",
            "description": build_collections_description(),
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
    )

    return tools


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

    def calculate_cost(
        self,
        input_tokens,
        output_tokens,
        cached_tokens=0,
        model=None,
        input_price_per_m=None,
        output_price_per_m=None,
        cached_price_per_m=None,
    ):
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

    def __init__(self, api_key, qdrant_client, primary_collection, secondary_collections, embedding_client):
        self.client = openai.OpenAI(api_key=api_key)
        self.qdrant_client = qdrant_client
        self.primary_collection = primary_collection
        self.secondary_collections = secondary_collections
        self.embedding_client = embedding_client
        self.tools = build_tools()

    # ---- Knowledge base search (called when agent uses the tool) ----

    def _search_single_collection(self, collection_name, query_embedding, keywords=None, limit=5):
        """Search a single Qdrant collection and return formatted results."""
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
                collection_name=collection_name,
                query=query_embedding,
                limit=limit,
                with_payload=True,
            ).points
        else:
            vector_results = self.qdrant_client.query_points(
                collection_name=collection_name,
                query=query_embedding,
                limit=limit,
                with_payload=True,
            ).points
            filtered_results, _ = self.qdrant_client.scroll(
                collection_name=collection_name,
                scroll_filter=keyword_filter,
                limit=3,
            )
            filtered_ids = set(point.id for point in filtered_results)
            combined = list(filtered_results)
            for r in vector_results:
                if r.id not in filtered_ids:
                    combined.append(r)
                if len(combined) >= limit:
                    break
            results = combined[:limit]

        # Format results for the agent
        documents = []
        for result in results:
            documents.append(
                {
                    "content": result.payload.get("content", ""),
                    "title": result.payload.get("metadata", {}).get("title", ""),
                    "url": result.payload.get("metadata", {}).get("url", ""),
                    "score": getattr(result, "score", "keyword_match"),
                    "collection": collection_name,
                }
            )

        return documents

    def search_knowledge_base(self, query, keywords=None):
        """Execute a Qdrant knowledge base search across all collections."""
        query_embedding = self.embedding_client.create_embedding(query)

        # Search primary collection (always)
        results = self._search_single_collection(
            self.primary_collection, query_embedding, keywords, limit=5
        )

        # Search secondary collections (limit 2 each)
        for coll_name in self.secondary_collections:
            secondary_results = self._search_single_collection(
                coll_name, query_embedding, keywords, limit=2
            )
            results.extend(secondary_results)

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for doc in results:
            url = doc.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(doc)
            elif not url:
                unique_results.append(doc)

        return unique_results[:10]

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
            api_input.append(
                {
                    "role": msg["role"],
                    "content": msg["content"],
                }
            )

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

                    print(
                        f"[Agent] Searching knowledge base: query='{query}', keywords={keywords}"
                    )
                    results = self.search_knowledge_base(query, keywords)

                    # Send results back to the agent and stream the final answer
                    followup_stream = self.client.responses.create(
                        model=model_config.CHAT_MODEL,
                        instructions=system_prompt,
                        input=api_input
                        + [
                            {
                                "type": "function_call",
                                "call_id": call_id,
                                "name": "search_knowledge_base",
                                "arguments": args_str,
                            },
                            {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": json.dumps(results, ensure_ascii=False),
                            },
                        ],
                        tools=self.tools,
                        stream=True,
                    )

                    for followup_event in followup_stream:
                        if followup_event.type == "response.output_text.delta":
                            collected_text.append(followup_event.delta)
                            stream_callback(followup_event.delta)
                        elif followup_event.type == "response.completed":
                            if (
                                hasattr(followup_event.response, "usage")
                                and followup_event.response.usage
                            ):
                                total_input_tokens += getattr(
                                    followup_event.response.usage, "input_tokens", 0
                                )
                                total_output_tokens += getattr(
                                    followup_event.response.usage, "output_tokens", 0
                                )

                                details = getattr(
                                    followup_event.response.usage,
                                    "prompt_tokens_details",
                                    None,
                                )
                                if details:
                                    total_cached_tokens += (
                                        getattr(details, "cached_tokens", 0)
                                        if hasattr(details, "cached_tokens")
                                        else details.get("cached_tokens", 0)
                                    )

                # Reset for next potential call
                current_call_id = None
                current_call_args = ""

            # Response completed — capture usage stats
            elif event.type == "response.completed":
                if hasattr(event.response, "usage") and event.response.usage:
                    total_input_tokens += getattr(
                        event.response.usage, "input_tokens", 0
                    )
                    total_output_tokens += getattr(
                        event.response.usage, "output_tokens", 0
                    )

                    details = getattr(
                        event.response.usage, "prompt_tokens_details", None
                    )
                    if details:
                        total_cached_tokens += (
                            getattr(details, "cached_tokens", 0)
                            if hasattr(details, "cached_tokens")
                            else details.get("cached_tokens", 0)
                        )

        full_response = "".join(collected_text)
        cost_usd = self.calculate_cost(
            total_input_tokens,
            total_output_tokens,
            cached_tokens=total_cached_tokens,
            model=model_config.CHAT_MODEL,
        )

        return {
            "full_response": full_response,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "cost_usd": cost_usd,
        }


# ============================================================
# GOOGLE IMPLEMENTATION (Gemini)
# ============================================================


class GoogleClient(LLMClient):
    """Google Gemini provider using the generate_content API."""

    def __init__(self, api_key, qdrant_client, primary_collection, secondary_collections, embedding_client):
        from google import genai
        from google.genai import types as genai_types

        self.client = genai.Client(api_key=api_key)
        self.genai_types = genai_types
        self.qdrant_client = qdrant_client
        self.primary_collection = primary_collection
        self.secondary_collections = secondary_collections
        self.embedding_client = embedding_client
        self.model_name = model_config.CHAT_MODEL
        self.tools = self._build_google_tools()

    def _build_google_tools(self):
        T = self.genai_types

        kb_function = T.FunctionDeclaration(
            name="search_knowledge_base",
            description=build_collections_description(),
            parameters=T.Schema(
                type=T.Type.OBJECT,
                properties={
                    "query": T.Schema(
                        type=T.Type.STRING,
                        description="The search query in Swedish",
                    ),
                    "keywords": T.Schema(
                        type=T.Type.ARRAY,
                        items=T.Schema(type=T.Type.STRING),
                        description=(
                            "Optional specific keywords for filtering "
                            "(names of people, places, dates, addresses)"
                        ),
                    ),
                },
                required=["query"],
            ),
        )

        tools = [T.Tool(function_declarations=[kb_function])]

        if model_config.WEB_SEARCH_ENABLED:
            tools.append(T.Tool(google_search=T.GoogleSearch()))

        return tools

    def _search_single_collection(self, collection_name, query_embedding, keywords=None, limit=5):
        """Search a single Qdrant collection and return formatted results."""
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

        if keyword_filter is None:
            results = self.qdrant_client.query_points(
                collection_name=collection_name,
                query=query_embedding,
                limit=limit,
                with_payload=True,
            ).points
        else:
            vector_results = self.qdrant_client.query_points(
                collection_name=collection_name,
                query=query_embedding,
                limit=limit,
                with_payload=True,
            ).points
            filtered_results, _ = self.qdrant_client.scroll(
                collection_name=collection_name,
                scroll_filter=keyword_filter,
                limit=3,
            )
            filtered_ids = set(point.id for point in filtered_results)
            combined = list(filtered_results)
            for r in vector_results:
                if r.id not in filtered_ids:
                    combined.append(r)
                if len(combined) >= limit:
                    break
            results = combined[:limit]

        documents = []
        for result in results:
            documents.append(
                {
                    "content": result.payload.get("content", ""),
                    "title": result.payload.get("metadata", {}).get("title", ""),
                    "url": result.payload.get("metadata", {}).get("url", ""),
                    "score": getattr(result, "score", "keyword_match"),
                    "collection": collection_name,
                }
            )

        return documents

    def search_knowledge_base(self, query, keywords=None):
        """Execute a Qdrant knowledge base search across all collections."""
        query_embedding = self.embedding_client.create_embedding(query)

        results = self._search_single_collection(
            self.primary_collection, query_embedding, keywords, limit=5
        )

        for coll_name in self.secondary_collections:
            secondary_results = self._search_single_collection(
                coll_name, query_embedding, keywords, limit=2
            )
            results.extend(secondary_results)

        seen_urls = set()
        unique_results = []
        for doc in results:
            url = doc.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(doc)
            elif not url:
                unique_results.append(doc)

        return unique_results[:10]

    def run_agent(self, messages, system_prompt, stream_callback):
        """
        Run the agentic loop with Gemini.

        Handles:
        - google_search: automatic (handled server-side by Gemini)
        - function_call (search_knowledge_base): we execute and feed back
        - text output: streamed via callback
        """
        T = self.genai_types
        total_input_tokens = 0
        total_output_tokens = 0
        collected_text = []

        # Convert messages to Google Content format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(
                T.Content(
                    role=role,
                    parts=[T.Part(text=msg["content"])],
                )
            )

        # Track the latest function call for follow-up
        function_call_name = None
        function_call_args = None
        function_call_content = None  # Full model Content (preserves thought_signature)

        # Collect grounding metadata from the initial stream
        grounding_chunks = []

        # Initial streaming call
        stream = self.client.models.generate_content_stream(
            model=self.model_name,
            contents=contents,
            config=T.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=self.tools,
                toolConfig=T.ToolConfig(
                    includeServerSideToolInvocations=True,
                ),
                automaticFunctionCalling=T.AutomaticFunctionCallingConfig(
                    disable=True,
                ),
            ),
        )

        for chunk in stream:
            has_text_part = False
            has_function_call = False

            if chunk.candidates and chunk.candidates[0].content.parts:
                for part in chunk.candidates[0].content.parts:
                    if part.text:
                        has_text_part = True
                    if part.function_call:
                        has_function_call = True
                        function_call_name = part.function_call.name
                        function_call_args = part.function_call.args
                        function_call_content = chunk.candidates[0].content

                # Capture grounding metadata from the last candidate
                gm = chunk.candidates[0].grounding_metadata
                if gm and gm.grounding_chunks:
                    grounding_chunks = gm.grounding_chunks

            if has_text_part and chunk.text:
                collected_text.append(chunk.text)
                stream_callback(chunk.text)

            if chunk.usage_metadata:
                total_input_tokens = chunk.usage_metadata.prompt_token_count
                total_output_tokens = chunk.usage_metadata.candidates_token_count

        # If the model called our knowledge base function, execute and follow up
        if function_call_name == "search_knowledge_base":
            args = {k: v for k, v in function_call_args.items()}
            query = args.get("query", "")
            keywords = args.get("keywords", [])

            print(
                f"[Agent/Google] Searching knowledge base: query='{query}', keywords={keywords}"
            )
            results = self.search_knowledge_base(query, keywords)

            function_response_content = T.Content(
                role="tool",
                parts=[
                    T.Part.from_function_response(
                        name=function_call_name,
                        response={"result": results},
                    )
                ],
            )

            followup_contents = list(contents) + [
                function_call_content,
                function_response_content,
            ]

            followup_stream = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=followup_contents,
                config=T.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=self.tools,
                    toolConfig=T.ToolConfig(
                        includeServerSideToolInvocations=True,
                    ),
                    automaticFunctionCalling=T.AutomaticFunctionCallingConfig(
                        disable=True,
                    ),
                ),
            )

            for fu_chunk in followup_stream:
                fu_has_text = False
                if fu_chunk.candidates and fu_chunk.candidates[0].content.parts:
                    for p in fu_chunk.candidates[0].content.parts:
                        if p.text:
                            fu_has_text = True
                            break
                    # Capture follow-up grounding metadata too
                    gm = fu_chunk.candidates[0].grounding_metadata
                    if gm and gm.grounding_chunks:
                        grounding_chunks = gm.grounding_chunks

                if fu_has_text and fu_chunk.text:
                    collected_text.append(fu_chunk.text)
                    stream_callback(fu_chunk.text)
                if fu_chunk.usage_metadata:
                    total_input_tokens = fu_chunk.usage_metadata.prompt_token_count
                    total_output_tokens = fu_chunk.usage_metadata.candidates_token_count

        full_response = "".join(collected_text)

        # Replace citation markers with clickable links (final pass for Directus)
        if grounding_chunks:
            full_response = self._resolve_grounding_refs(
                full_response, grounding_chunks
            )

        cost_usd = self.calculate_cost(
            total_input_tokens,
            total_output_tokens,
            model=self.model_name,
        )

        return {
            "full_response": full_response,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "cost_usd": cost_usd,
        }

    @staticmethod
    def _resolve_grounding_refs(text, grounding_chunks):
        """Replace [N] citations with clickable markdown links."""
        if not grounding_chunks:
            return text

        url_map = []
        for gc in grounding_chunks:
            web = getattr(gc, "web", None)
            if web:
                uri = getattr(web, "uri", "")
                title = getattr(web, "title", "") or uri
                if uri:
                    url_map.append((uri, title))

        if not url_map:
            return text

        import re

        def replace_ref(m):
            idx = int(m.group(1))
            for offset in (0, -1):
                check = idx + offset
                if 0 <= check < len(url_map):
                    uri, title = url_map[check]
                    return f"[{title}]({uri})"
            return m.group(0)

        return re.sub(r"\[(\d+)\]", replace_ref, text)


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


def get_client(api_keys, qdrant_client, primary_collection):
    """
    Factory function — returns the correct LLMClient based on
    the CHAT_PROVIDER setting in model_config.py.
    """
    embedding_client = get_embedding_client(api_keys)
    provider = getattr(model_config, "CHAT_PROVIDER", "openai")
    secondary_collections = getattr(model_config, "SECONDARY_COLLECTIONS", {})
    secondary_names = list(secondary_collections.keys())

    if provider == "openai":
        return OpenAIClient(
            api_keys.get("openai"), qdrant_client, primary_collection, secondary_names, embedding_client
        )
    elif provider == "google":
        return GoogleClient(
            api_keys.get("google"), qdrant_client, primary_collection, secondary_names, embedding_client
        )
    else:
        raise ValueError(f"Unsupported chat provider: {provider}")
