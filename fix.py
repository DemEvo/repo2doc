#!/usr/bin/env python3
import argparse
import asyncio
import logging
import sys
import re
import os
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from nblm_core import init_client, configure_chat, send_query

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROMPTS_DIR = Path("./Prompts")
TRANSCRIPT_QUERY = "Выведи полный транскрипт для {url} (целевой язык вывода транскрипта русский)"
DEFAULT_TRANSCRIPT_TIMEOUT = 600

console = Console()
logging.getLogger("notebooklm").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NotebookLM Transcriptor CLI")
    parser.add_argument("--nb_id", required=True)
    parser.add_argument("--list", required=True, dest="list_path")
    parser.add_argument("--prompt", required=True, dest="prompt_name")
    parser.add_argument("--prefix", default="Transcript")
    parser.add_argument("--max_words", type=int, default=128000)
    parser.add_argument("--length", default="long", choices=["default", "short", "long"])
    return parser


def is_valid_url(line: str) -> bool:
    return bool(re.match(r"^https?://", line.strip()))


async def cleanup_notebook(client: Any, nb_id: str) -> None:
    try:
        sources = await client.sources.list(nb_id)
        for src in sources:
            src_id = getattr(src, 'id', None)
            if src_id: await client.sources.delete(nb_id, src_id)
    except Exception:
        pass


async def run_transcriptor(args: argparse.Namespace) -> None:
    # 1. Init
    prompt_path = PROMPTS_DIR / f"{args.prompt_name}.md"
    sys_prompt_text = prompt_path.read_text(encoding="utf-8").strip()

    list_file = Path(args.list_path)
    urls = [line.strip() for line in list_file.read_text(encoding="utf-8").splitlines() if is_valid_url(line)]

    if not urls:
        console.print("[yellow]No URLs found.[/yellow]")
        return

    # Отключаем лишний мусор для TERM=dumb (многопоток)
    is_dumb = os.environ.get("TERM") == "dumb"
    if not is_dumb:
        console.print(Panel(f"NB: {args.nb_id}\nURLs: {len(urls)}", title="Starter"))

    client = await init_client()
    async with client:
        await cleanup_notebook(client, args.nb_id)

        current_part = 1
        words_in_current_file = 0
        total_processed = 0
        total_errors = 0

        for idx, url in enumerate(urls):
            prefix_log = f"[{args.prefix}] [{idx + 1}/{len(urls)}]"
            console.print(f"{prefix_log} Processing: {url[:50]}...")

            try:
                await configure_chat(client, args.nb_id, sys_prompt_text, args.length)
                await client.sources.add_url(args.nb_id, url)

                answer = await send_query(
                    client, args.nb_id, TRANSCRIPT_QUERY.format(url=url),
                    request_timeout=DEFAULT_TRANSCRIPT_TIMEOUT,
                    on_retry=lambda a, m, d, e: console.print(f"  {prefix_log} [yellow]Retry {a}/{m}...[/yellow]")
                )

                if not answer or not answer.strip() or "[!ERROR]" in answer:
                    content = f"\n\n[!ERROR] EMPTY RESPONSE FOR: {url}\n\n"
                    word_cnt = 0
                    total_errors += 1
                else:
                    answer = re.sub(r'\s*\[\d+(?:,\s*\d+)*\]', '', answer)
                    content = f"\n\n{answer}\n\n---\n"
                    word_cnt = len(answer.split())

                if words_in_current_file > 0 and (words_in_current_file + word_cnt > args.max_words):
                    current_part += 1
                    words_in_current_file = 0
                    console.print(f"  {prefix_log} [yellow]Rotation -> Part {current_part}[/yellow]")

                with open(f"{args.prefix}_part{current_part}.md", "a", encoding="utf-8") as f:
                    f.write(content)

                words_in_current_file += word_cnt
                total_processed += 1
                await cleanup_notebook(client, args.nb_id)

            except Exception as e:
                console.print(f"  {prefix_log} [red]Error: {e}[/red]")
                total_errors += 1

            await asyncio.sleep(1)

        # Финальный отчет (исправленный)
        if not is_dumb:
            console.print("\n", Panel.fit(
                f"Processed: {total_processed}\nErrors: {total_errors}\nParts: {current_part}",
                title="Done", border_style="green"
            ))


def main():
    args = build_parser().parse_args()
    try:
        asyncio.run(run_transcriptor(args))
    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == "__main__":
    main()