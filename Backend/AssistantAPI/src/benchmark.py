#!/usr/bin/env python3
"""
Benchmark tool — compare AI models on Falkenberg municipality questions.

Measures response quality, token usage, cost, and latency across models.
Runs fully integrated (Qdrant, web search) but does NOT save to Directus.

Usage:
    python benchmark.py
    python benchmark.py --models gpt-4o gemini-3.1-flash-lite
    python benchmark.py --models gpt-4o gemini-3.1-flash-lite --questions my_questions.json
    python benchmark.py --models gpt-4o --output results.json
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from qdrant_client import QdrantClient

import model_config
from llm_client import get_client

# ============================================================
# PATH CONFIG
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_KEYS_PATH = os.path.join(BASE_DIR, "..", "..", "data", "API_KEYS.env")
QDRANT_URL = "https://qdrant.utvecklingfalkenberg.se"
COLLECTION_NAME = "FalkenbergsKommunsHemsida_RAG"

MODEL_PROVIDER_MAP = {
    "gpt-5.4-mini": "openai",
    "gpt-4o": "openai",
    "gemini-3.1-flash-lite": "google",
    "gemini-3-flash-preview": "google",
}


# ============================================================
# DEFAULT BENCHMARK QUESTIONS
# ============================================================

DEFAULT_QUESTIONS = [
    # ---- Bygglov & boende ----
    {
        "category": "bygglov_boende",
        "question": "Hur ansöker jag om bygglov i Falkenbergs kommun? Vad kostar det och hur lång tid tar handläggningen?",
    },
    {
        "category": "bygglov_boende",
        "question": "Hur ställer jag mig i bostadskön hos FABO och hur fungerar deras hyressättning?",
    },
    {
        "category": "bygglov_boende",
        "question": "Jag vill hyra en lägenhet i Falkenberg. Vilka alternativ finns och hur ansöker jag?",
    },
    # ---- Avfall & vatten ----
    {
        "category": "avfall_vatten",
        "question": "När är min sophämtning i Falkenberg? Hur vet jag vilken vecka det är och vad gör jag om soporna inte hämtas?",
    },
    {
        "category": "avfall_vatten",
        "question": "Hur anmäler jag en vattenläcka till VIVAB? Vart vänder jag mig akut?",
    },
    # ---- Skola & omsorg ----
    {
        "category": "skola_omsorg",
        "question": "Hur ansöker jag om förskoleplats i Falkenbergs kommun och vilka förskolor finns att välja på?",
    },
    {
        "category": "skola_omsorg",
        "question": "Vilka grundskolor finns i Falkenberg och hur gör jag för att byta skola för mitt barn?",
    },
    # ---- Turism ----
    {
        "category": "turism",
        "question": "Vad finns det för sevärdheter och aktiviteter i Falkenberg? Ge mig tips på saker att göra som besökare.",
    },
    {
        "category": "turism",
        "question": "Vilka restauranger och caféer rekommenderar du i centrala Falkenberg?",
    },
    # ---- Kontakt & service ----
    {
        "category": "kontakt_service",
        "question": "Vilket telefonnummer har kontaktcenter i Falkenbergs kommun och vilka öppettider har de?",
    },
    {
        "category": "kontakt_service",
        "question": "Hur ansöker jag om svenskt pass i Falkenberg? Vad behöver jag ta med mig?",
    },
    # ---- Kommunal info ----
    {
        "category": "kommunal_info",
        "question": "Vilka nämnder och förvaltningar finns i Falkenbergs kommun och vad ansvarar de för?",
    },
    {
        "category": "kommunal_info",
        "question": "Var hittar jag detaljplaner och byggprojekt i Falkenberg? Hur kan jag lämna synpunkter?",
    },
    # ---- FABO ----
    {
        "category": "fabo",
        "question": "Hur gör jag en felanmälan till FABO om något är sönder i min lägenhet, till exempel ett vattenläckage?",
    },
    # ---- VIVAB ----
    {
        "category": "vivab",
        "question": "Hur sorterar jag hushållsavfall i Falkenbergs kommun? Var finns närmaste återvinningsstation?",
    },
]


# ============================================================
# HELPERS
# ============================================================


def load_api_key(key_variable):
    if not os.path.exists(API_KEYS_PATH):
        print(f"Error: API keys file not found at {API_KEYS_PATH}")
        sys.exit(1)
    load_dotenv(dotenv_path=API_KEYS_PATH)
    key = os.getenv(key_variable)
    if not key:
        print(f"Error: {key_variable} not found in {API_KEYS_PATH}")
        sys.exit(1)
    return key


def build_system_prompt(user_input):
    utc_time = datetime.now(timezone.utc).replace(microsecond=0)
    current_date_time = utc_time.astimezone(ZoneInfo("Europe/Stockholm"))
    current_date_time_str = current_date_time.strftime("%Y-%m-%dT%H:%M:%S")

    domain_descriptions = "\n".join(
        f"      - **{domain}**: {desc}"
        for domain, desc in model_config.ALLOWED_DOMAINS_INFO.items()
    )

    # Build tools section (varies based on WEB_SEARCH_ENABLED)
    if model_config.WEB_SEARCH_ENABLED:
        tools_section = """    VERKTYG:
    Du har tillgång till två sökverktyg:
    1. **search_knowledge_base** — Sök i Falkenbergs kommuns kunskapsbas (indexerade dokument, PDF:er och webbsidor från kommun.falkenberg.se). Använd detta för detaljerad kommunal information som regler, kontaktuppgifter och officiella dokument.
    2. **web_search** — Sök på webben (begränsat till specifika domäner). Använd detta för aktuell/uppdaterad information som kanske inte finns i kunskapsbasen.

    WEBBSÖKNINGENS DOMÄNER OCH INNEHÅLL:
""" + domain_descriptions + """

    VÄGLEDNING FÖR VERKTYGSVAL:
    - Bygglov, förskola, skola, socialtjänst, detaljplaner → search_knowledge_base
    - Lägenheter/hyra (fabo.se), sopor/vatten (vivab.se), evenemang/turism (falkenberg.se) → web_search
"""
    else:
        tools_section = """    VERKTYG:
    Du har tillgång till ett sökverktyg:
    1. **search_knowledge_base** — Sök i Falkenbergs kommuns kunskapsbas (indexerade dokument, PDF:er och webbsidor från kommun.falkenberg.se). Använd detta för detaljerad kommunal information som regler, kontaktuppgifter och officiella dokument.
"""

    return f"""Ditt namn är Falkis. Du är en professionell, gullig och hjälpsam falk-assistent som ENBART svarar på frågor relaterade till Falkenbergs kommun och de tillhandahållna dokumenten.

    SÄKERHETSREGLER:
    - Du får under inga omständigheter använda nedsättande, rasistiskt, kränkande eller hatiskt språk.
    - Om användaren ställer frågor som är stötande, ska du artigt svara att du endast är här för att hjälpa till med frågor om Falkenbergs kommun.
    - Om du är 100% säker på att frågan saknar koppling till Falkenbergs kommun (t.ex. allmänna fakta om rymden, utländska kändisar), ska du svara: 
    "Jag är Falkis och jag hjälper bara till med frågor om Falkenbergs kommun. Kan jag hjälpa dig med något som rör vår kommun istället?"
    - VIKTIGT: Namn på personer (t.ex. lokalpolitiker som Per Svensson), projekt (t.ex. Agenda 2030) eller frågor om vem du är ("Vem är du/Falkis?") ÄR relaterade till ditt uppdrag. Om du är osäker på om ett namn/ämne rör kommunen: ANVÄND DINA SÖKVERKTYG FÖRST innan du avvisar frågan!

{tools_section}
    INSTRUKTIONER FÖR SVAR:
    1. Använd dina sökverktyg för att hitta relevant information innan du svarar på faktafrågor.{' Välj rätt verktyg baserat på frågan (se VÄGLEDNING FÖR VERKTYGSVAL ovan).' if model_config.WEB_SEARCH_ENABLED else ''}
    2. Om svaret inte hittas via verktygen, säg att du inte hittar informationen men hänvisa gärna till kontaktcenter tel:0346-88 60 00 / mail:kontaktcenter@falkenberg.se
    3. Svara på samma språk som användaren skriver på ({user_input}).
    4. Dagens datum och tid är {current_date_time_str}.
    5. För enkla hälsningar och uppföljningsfrågor som inte kräver ny information, svara direkt utan att använda verktyg.
    
    KÄLLHANTERING:
    - Varje faktapåstående ska ha en klickbar länk till exakt källa.
    - Använd beskrivande text i länken, t.ex. [Falkenbergs kommuns bygglovssida](https://...)
      eller [FABO - Betala hyra](https://fabo.se/hyresinformation/...).
    - Ange aldrig bara domännamn som (https://fabo.se) — länka alltid till den specifika
      undersidan där informationen finns.
    - Ange aldrig fotnotsnummer som [1] eller [3] — de ska alltid ersättas med beskrivande länkar.
    - Använd rena URL:er utan spårningsparametrar (?utm_source=...).
    """


def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{seconds // 60:.0f}m {seconds % 60:.0f}s"


# ============================================================
# MARKDOWN REPORT
# ============================================================


def escape_md(text):
    """Escape markdown special characters in text."""
    return text.replace("|", "\\|")


def write_markdown_report(results, md_path):
    """Write a formatted markdown report from benchmark results."""
    ts = results["timestamp"][:19].replace("T", " ")
    models = results["models"]
    summary = results.get("summary", {})
    questions = results["questions"]

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Falkis Benchmark — {ts}\n\n")
        f.write(f"**Modeller testade:** {', '.join(f'`{m}`' for m in models)}\n")
        f.write(f"**Antal frågor:** {len(questions)}\n\n")

        # Summary table
        f.write("## Sammanfattning\n\n")
        f.write(
            "| Modell | Total kostnad | Totala tokens | Input tokens | Output tokens | Snittid | Snitt output |\n"
        )
        f.write(
            "|--------|-------------:|-------------:|-------------:|--------------:|-------:|------------:|\n"
        )
        for model in models:
            s = summary.get(model, {})
            cost = s.get("total_cost", 0)
            total_tok = s.get("total_tokens", 0)
            in_tok = s.get("total_input_tokens", 0)
            out_tok = s.get("total_output_tokens", 0)
            avg_t = s.get("avg_time_seconds", 0)
            avg_out = s.get("avg_output_tokens", 0)
            f.write(
                f"| `{model}` | ${cost:.4f} | {total_tok:,} | {in_tok:,} | {out_tok:,} | {avg_t:.1f}s | {avg_out:.0f} |\n"
            )

        f.write("\n---\n\n")

        # Each question
        for idx, q in enumerate(questions, 1):
            category = q.get("category", "general").replace("_", " ").title()
            question = q["question"]

            f.write(f"## {idx}. [{category}] {question}\n\n")

            for model in models:
                r = q.get("results", {}).get(model, {})
                error = r.get("error")
                response = r.get("response", "")
                in_tok = r.get("input_tokens", "?")
                out_tok = r.get("output_tokens", "?")
                cost = r.get("cost_usd", "?")
                time_s = r.get("time_seconds", "?")

                f.write(f"### {model}\n\n")
                if error:
                    f.write(f"> ⚠ **Error:** {escape_md(error)}\n\n")
                    continue

                f.write(f"**{out_tok} output tokens · ${cost} · {time_s}s**\n\n")

                # Write the response as markdown (it's already in markdown format)
                f.write(response.strip())
                f.write("\n\n")

            f.write("---\n\n")

    return md_path


# ============================================================
# BENCHMARK RUNNER
# ============================================================


def run_benchmark(models, questions, output_path=None):
    print(f"\n{'=' * 72}")
    print(f"  FALKIS BENCHMARK")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Models:     {', '.join(models)}")
    print(f"  Questions:  {len(questions)}")
    print(f"  Qdrant:     enabled")
    print(f"  Web search: enabled")
    print(f"  Directus:   disabled (benchmark mode)")
    print(f"{'=' * 72}")

    # Load API keys
    api_keys = {
        "openai": load_api_key("OPENAI_API_KEY"),
        "google": load_api_key("GOOGLE_API_KEY"),
    }

    # Connect to Qdrant
    qdrant_client = QdrantClient(
        url=QDRANT_URL,
        port=443,
        https=True,
        api_key=load_api_key("QDRANT_API_KEY"),
    )

    results = {
        "timestamp": datetime.now().isoformat(),
        "models": models,
        "questions": [],
    }

    for idx, q_data in enumerate(questions, 1):
        question = q_data["question"]
        category = q_data.get("category", "general")
        print(f"\n{'─' * 72}")
        print(f"  [{idx}/{len(questions)}] ({category})")
        print(f"  Q: {question[:120]}")

        question_entry = {
            "category": category,
            "question": question,
            "results": {},
        }

        for model in models:
            provider = MODEL_PROVIDER_MAP.get(model)
            if not provider:
                print(f"  ! Unknown model: {model}, skipping")
                continue

            # Override config and create a fresh client for this model
            model_config.CHAT_PROVIDER = provider
            model_config.CHAT_MODEL = model

            try:
                llm = get_client(api_keys, qdrant_client, COLLECTION_NAME)
            except Exception as e:
                print(f"  ! Failed to create client for {model}: {e}")
                question_entry["results"][model] = {"error": str(e)}
                continue

            system_prompt = build_system_prompt(question)
            messages = [{"role": "user", "content": question}]
            collected = []

            def stream_cb(chunk):
                collected.append(chunk)

            start = time.time()
            try:
                result = llm.run_agent(messages, system_prompt, stream_cb)
                elapsed = time.time() - start

                question_entry["results"][model] = {
                    "response": result["full_response"],
                    "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"],
                    "cost_usd": result["cost_usd"],
                    "time_seconds": round(elapsed, 2),
                }

                status = result.get("full_response", "")
                preview = status[:80].replace("\n", " ")
                print(
                    f"  [{model}] {result['output_tokens']:>5d} tok · ${result['cost_usd']:<8.6f} · {elapsed:>5.1f}s"
                )
                print(f"           {preview}...")

            except Exception as e:
                elapsed = time.time() - start
                print(f"  [{model}] ERROR after {elapsed:.1f}s: {e}")
                question_entry["results"][model] = {
                    "response": None,
                    "error": str(e),
                    "time_seconds": round(elapsed, 2),
                }

        results["questions"].append(question_entry)

    # ---- Summary ----
    summary = {}
    for model in models:
        entries = [
            q["results"].get(model, {})
            for q in results["questions"]
            if model in q["results"]
        ]
        valid = [
            e
            for e in entries
            if e.get("output_tokens") is not None and e.get("cost_usd") is not None
        ]
        if valid:
            total_cost = sum(e["cost_usd"] for e in valid)
            total_in = sum(e["input_tokens"] for e in valid)
            total_out = sum(e["output_tokens"] for e in valid)
            avg_time = sum(e["time_seconds"] for e in valid) / len(valid)
            avg_out = sum(e["output_tokens"] for e in valid) / len(valid)

            summary[model] = {
                "total_cost": round(total_cost, 6),
                "total_input_tokens": total_in,
                "total_output_tokens": total_out,
                "total_tokens": total_in + total_out,
                "avg_time_seconds": round(avg_time, 2),
                "avg_output_tokens": round(avg_out, 1),
                "success_rate": f"{len(valid)}/{len(entries)}",
            }

    results["summary"] = summary

    # Save results
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(BASE_DIR, f"benchmark_results_{timestamp}.json")

    md_path = output_path.replace(".json", ".md")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    write_markdown_report(results, md_path)

    # Print summary table
    print(f"\n{'=' * 72}")
    print(f"  SUMMARY")
    print(f"{'=' * 72}")
    print(
        f"  {'Model':<30s} {'Cost $':>12s} {'Tokens':>10s} {'Avg Time':>10s} {'Avg Out':>10s}"
    )
    print(f"  {'─' * 72}")
    for model, s in summary.items():
        print(
            f"  {model:<30s} ${s['total_cost']:<10.6f} {s['total_tokens']:>7d}   {s['avg_time_seconds']:>6.1f}s  {s['avg_output_tokens']:>7.1f}"
        )
    print(f"{'─' * 72}")

    if len(models) == 2 and len(summary) == 2:
        m1, m2 = models
        if m1 in summary and m2 in summary:
            cost_ratio = (
                summary[m2]["total_cost"] / summary[m1]["total_cost"]
                if summary[m1]["total_cost"] > 0
                else float("inf")
            )
            time_ratio = (
                summary[m2]["avg_time_seconds"] / summary[m1]["avg_time_seconds"]
                if summary[m1]["avg_time_seconds"] > 0
                else float("inf")
            )
            print(f"\n  Quick comparison:")
            print(f"    {m1} vs {m2}:")
            print(f"    - Cost:   {m2} is {cost_ratio:.1f}x the cost of {m1}")
            print(f"    - Speed:  {m2} is {time_ratio:.1f}x the time of {m1}")

    print(f"{'=' * 72}")
    print(f"  JSON: {output_path}")
    print(f"  Markdown: {md_path}")
    print(f"{'=' * 72}\n")

    return results


# ============================================================
# CLI
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="Falkis Benchmark — compare AI models on Falkenberg municipality questions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python benchmark.py\n"
            "  python benchmark.py --models gpt-4o gemini-3.1-flash-lite\n"
            "  python benchmark.py -m gpt-4o -o my_results.json\n"
            "  python benchmark.py --models gpt-4o gemini-3.1-flash-lite --questions custom_set.json\n"
        ),
    )
    parser.add_argument(
        "--models",
        "-m",
        nargs="+",
        default=["gpt-4o", "gemini-3.1-flash-lite"],
        choices=list(MODEL_PROVIDER_MAP.keys()),
        help="Models to benchmark (default: gpt-4o gemini-3.1-flash-lite)",  # noqa: E501
    )
    parser.add_argument(
        "--questions",
        "-q",
        type=str,
        default=None,
        help="Path to a JSON file with custom questions",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output JSON file path (default: benchmark_results_TIMESTAMP.json)",
    )

    args = parser.parse_args()

    # Load questions
    if args.questions:
        q_path = os.path.join(BASE_DIR, args.questions)
        if not os.path.exists(q_path):
            print(f"Error: Questions file not found: {q_path}")
            sys.exit(1)
        with open(q_path, "r", encoding="utf-8") as f:
            questions = json.load(f)
        print(f"Loaded {len(questions)} custom questions from {q_path}")
    else:
        questions = DEFAULT_QUESTIONS[
            5:10
        ]  # For quicker testing, use a subset of default questions
        print(f"Using {len(questions)} default benchmark questions")

    run_benchmark(args.models, questions, args.output)


if __name__ == "__main__":
    main()
