#!/usr/bin/env python3
"""
Recipe agent TUI backed by the Claude Agent SDK.
"""

import argparse
import asyncio
import contextlib
import curses
import json
import os
import queue
import textwrap
import threading
from typing import Any, Dict, List, Tuple, Deque
from collections import deque

from traderjoes import TraderJoesAPI

import dotenv
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    tool,
)
from braintrust import init_logger


dotenv.load_dotenv()

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
MAX_TOOL_RESULTS = 8
BRAINTRUST_PROJECT = os.getenv("BRAINTRUST_PROJECT", "Trader Joes Recipe Agent")
DEFAULT_SYSTEM_PROMPT_FILE = os.getenv("SYSTEM_PROMPT_FILE", "SYSTEM.md")


def normalize_product(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sku": item.get("sku", ""),
        "item_title": item.get("item_title", ""),
        "item_description": item.get("item_description", ""),
        "retail_price": item.get("retail_price", ""),
        "sales_size": item.get("sales_size", ""),
        "sales_uom_description": item.get("sales_uom_description", ""),
        "availability": item.get("availability", ""),
        "url_key": item.get("url_key", ""),
    }


def _read_system_prompt(default_store_code: str) -> str:
    """
    Loads the system prompt from SYSTEM_PROMPT_FILE or uses the built-in default.
    """
    filenames = [
        os.getenv("SYSTEM_PROMPT_FILE", "SYSTEM.md"),
        "SYSTEM.md",
        "system.md",
    ]
    for filename in filenames:
        try:
            if filename.startswith("@"):
                filename = filename.lstrip("@")
            with open(filename, encoding="utf-8") as f:
                prompt = f.read().strip()
                # Optionally substitute store code variable if present in file
                # prompt = prompt.replace("{STORE_CODE}", default_store_code)
                print(prompt)
                return prompt
        except FileNotFoundError:
            continue
    # fallback default if not found
    return (
        "You are a pragmatic recipe-planning assistant. "
        "Use Trader Joe's catalog tools to ground ingredient suggestions in real products when helpful. "
        f"The default store code is {default_store_code}. "
        "Do not invent exact SKUs or prices without tool confirmation. "
        "If the user asks for a recipe, produce a recipe title, a short why-this-works note, "
        "an ingredient list that references Trader Joe's product matches when available, "
        "and concise cooking steps. "
        "If product data is incomplete, say what is confirmed versus inferred. "
        "Use tools before making product-specific claims."
    )


class TurnLog:
    def __init__(self, user_text: str):
        self.user_text = user_text
        self.assistant_chunks: List[str] = []
        self.tool_events: List[str] = []

    def assistant_text(self) -> str:
        return "\n\n".join(chunk for chunk in self.assistant_chunks if chunk).strip()


class ClaudeRecipeAgent:
    """
    Wraps Claude Agent SDK in a background asyncio loop so the curses UI can stay synchronous.
    """

    def __init__(self, api_key: str, model: str, store_code: str):
        if not api_key:
            raise SystemExit("ANTHROPIC_API_KEY is required")

        self.model = model
        self.store_code = store_code
        self.catalog_api = TraderJoesAPI(verbose=False)
        self.session_id = "default"
        self.turns: Deque[TurnLog] = deque()

        self.logger = None
        if os.getenv("BRAINTRUST_API_KEY"):
            try:
                self.logger = init_logger(project=BRAINTRUST_PROJECT)
            except Exception:
                self.logger = None

        self.output_queue: "queue.Queue[Tuple[str, str]]" = queue.Queue()
        self._loop = asyncio.new_event_loop()
        self._shutdown_event: asyncio.Event | None = None
        self._startup_error: Exception | None = None

        self._system_prompt_str = _read_system_prompt(self.store_code)
        self.client = ClaudeSDKClient(
            ClaudeAgentOptions(
                model=model,
                system_prompt=self._system_prompt_str,
                allowed_tools=["search_products", "lookup_skus", "Read", "Glob"],
                permission_mode="default",
                mcp_servers={"traderjoes": self._create_tj_mcp_server()},
            )
        )

        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10)
        if self._startup_error is not None:
            raise RuntimeError(
                f"Claude SDK startup failed: {self._startup_error}"
            ) from self._startup_error
        if not self._ready.is_set():
            raise RuntimeError("Claude SDK startup timed out")

    def _create_tj_mcp_server(self):
        api = self.catalog_api

        @tool(
            "search_products",
            "Search Trader Joe's products by keyword for a store.",
            {
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "Ingredient or product phrase to search for.",
                    },
                    "store_code": {
                        "type": "string",
                        "description": "Store code; omit to use current default.",
                    },
                },
                "required": ["search_term"],
            },
        )
        async def search_products(args: Dict[str, Any]):
            term = str(args.get("search_term", "")).strip()
            if not term:
                return {
                    "content": [{"type": "text", "text": "search_term is required"}],
                    "is_error": True,
                }

            code = str(args.get("store_code") or self.store_code)

            def _call():
                result = api.search_products(code, term) or {}
                items = result.get("data", {}).get("products", {}).get("items", [])
                normalized = [
                    normalize_product(item) for item in items[:MAX_TOOL_RESULTS]
                ]
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "store_code": code,
                                    "search_term": term,
                                    "total_results": len(items),
                                    "items": normalized,
                                },
                                ensure_ascii=True,
                            ),
                        }
                    ]
                }

            return await asyncio.to_thread(_call)

        @tool(
            "lookup_skus",
            "Look up specific Trader Joe's SKUs for the current or provided store.",
            {
                "type": "object",
                "properties": {
                    "skus": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "One or more SKU identifiers.",
                    },
                    "store_code": {
                        "type": "string",
                        "description": "Store code; omit to use current default.",
                    },
                },
                "required": ["skus"],
            },
        )
        async def lookup_skus(args: Dict[str, Any]):
            raw_skus = args.get("skus", [])
            filtered = [str(sku).strip() for sku in raw_skus if str(sku).strip()]
            if not filtered:
                return {
                    "content": [
                        {"type": "text", "text": "at least one SKU is required"}
                    ],
                    "is_error": True,
                }

            code = str(args.get("store_code") or self.store_code)

            def _call():
                result = api.get_products_by_skus(code, filtered) or {}
                items = result.get("data", {}).get("products", {}).get("items", [])
                normalized = [
                    normalize_product(item) for item in items[:MAX_TOOL_RESULTS]
                ]
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "store_code": code,
                                    "skus": filtered,
                                    "total_results": len(items),
                                    "items": normalized,
                                },
                                ensure_ascii=True,
                            ),
                        }
                    ]
                }

            return await asyncio.to_thread(_call)

        return create_sdk_mcp_server(
            name="traderjoes", version="1.0.0", tools=[search_products, lookup_skus]
        )

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as exc:
            self._startup_error = exc
            self._ready.set()

    async def _main(self):
        self._shutdown_event = asyncio.Event()
        await self.client.connect()
        self._ready.set()
        receiver = asyncio.create_task(self._pump_messages())
        await self._shutdown_event.wait()
        receiver.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await receiver
        await self.client.disconnect()

    def reset(self):
        self.session_id = os.urandom(4).hex()
        self.turns.clear()

    def set_store_code(self, store_code: str):
        self.store_code = store_code

    def send_user_message(self, text: str):
        turn = TurnLog(text)
        self.turns.append(turn)
        future = asyncio.run_coroutine_threadsafe(
            self.client.query(prompt=text, session_id=self.session_id),
            self._loop,
        )
        try:
            future.result(timeout=1)
        except Exception as exc:
            self.output_queue.put(("Error", f"Failed to send: {exc}"))

    async def _pump_messages(self):
        async for message in self.client.receive_messages():
            current = self.turns[0] if self.turns else None
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text = block.text.strip()
                        if text:
                            if current:
                                current.assistant_chunks.append(text)
                            self.output_queue.put(("Chef", text))
                    elif isinstance(block, ToolUseBlock):
                        summary = f"tool {block.name} -> {json.dumps(block.input)}"
                        if current:
                            current.tool_events.append(summary)
                        self.output_queue.put(("Tool", summary))
                    elif isinstance(block, ToolResultBlock):
                        summary = f"tool result {block.tool_use_id}: {block.content}"
                        if current:
                            current.tool_events.append(summary)
                        self.output_queue.put(("Tool", summary))
            elif isinstance(message, ResultMessage):
                self.output_queue.put(
                    (
                        "System",
                        f"Usage: prompt={message.prompt_tokens} output={message.output_tokens}",
                    )
                )
                if current:
                    if self.logger:
                        try:
                            self.logger.log(
                                input={
                                    "user": current.user_text,
                                    "session": self.session_id,
                                },
                                output={
                                    "assistant": current.assistant_text(),
                                    "tool_events": current.tool_events,
                                    "usage": {
                                        "prompt_tokens": message.prompt_tokens,
                                        "output_tokens": message.output_tokens,
                                    },
                                },
                            )
                        except Exception:
                            pass
                    self.turns.popleft()
            else:
                self.output_queue.put(("System", repr(message)))

    def close(self):
        if self._shutdown_event:
            self._loop.call_soon_threadsafe(self._shutdown_event.set)
        self._thread.join(timeout=5)

    def _system_prompt(self) -> str:
        # Not used; prompt is set once in __init__. Provided for compatibility if code elsewhere expects it.
        return self._system_prompt_str


class RecipeAgentTUI:
    def __init__(self, agent: ClaudeRecipeAgent):
        self.agent = agent
        self.entries: List[Tuple[str, str]] = [
            (
                "System",
                "Enter a recipe request. Commands: /help, /clear, /quit, /store <code>.",
            )
        ]
        self.input_buffer = ""
        self.status = self._status_text()
        self.running = True

    def run(self, stdscr):
        with contextlib.suppress(curses.error):
            curses.curs_set(1)
        stdscr.keypad(True)
        stdscr.timeout(200)  # allow periodic screen refresh to surface agent output

        while self.running:
            self._drain_events()
            self._render(stdscr)
            try:
                key = stdscr.get_wch()
            except curses.error:
                continue

            if key == curses.KEY_RESIZE:
                continue

            if key in ("\n", "\r"):
                self._submit()
                continue

            if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                self.input_buffer = self.input_buffer[:-1]
                continue

            if isinstance(key, str) and key.isprintable():
                self.input_buffer += key

    def _submit(self):
        text = self.input_buffer.strip()
        self.input_buffer = ""
        if not text:
            return

        if text.startswith("/"):
            self._handle_command(text)
            return

        self.entries.append(("You", text))
        self.status = "Waiting on Claude..."
        self.agent.send_user_message(text)

    def _handle_command(self, text: str):
        command, _, argument = text.partition(" ")
        command = command.lower()
        argument = argument.strip()

        if command in {"/quit", "/exit"}:
            self.running = False
            return

        if command in {"/clear", "/reset"}:
            self.agent.reset()
            self.entries = [
                (
                    "System",
                    "Conversation cleared. Commands: /help, /clear, /quit, /store <code>.",
                )
            ]
            self.status = self._status_text()
            return

        if command == "/store":
            if not argument:
                self.entries.append(("System", "Usage: /store <code>"))
                return
            self.agent.set_store_code(argument)
            self.entries.append(("System", f"Default store changed to {argument}."))
            self.status = self._status_text()
            return

        if command == "/help":
            self.entries.append(
                (
                    "System",
                    "Ask for recipes, substitutions, meal ideas, or shopping help. "
                    "Use /store <code> to change stores, /clear to reset the chat, and /quit to exit.",
                )
            )
            return

        self.entries.append(("System", f"Unknown command: {command}"))

    def _drain_events(self):
        while True:
            try:
                role, text = self.agent.output_queue.get_nowait()
                self.entries.append((role, text))
                self.status = self._status_text()
            except queue.Empty:
                break

    def _status_text(self) -> str:
        return f"store={self.agent.store_code}  model={self.agent.model}"

    def _render(self, stdscr):
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        transcript_height = max(1, height - 2)

        wrapped_lines = self._wrap_entries(max(20, width - 1))
        visible_lines = wrapped_lines[-transcript_height:]

        for row, line in enumerate(visible_lines):
            stdscr.addnstr(row, 0, line, max(1, width - 1))

        stdscr.attron(curses.A_REVERSE)
        stdscr.addnstr(
            height - 2, 0, self.status.ljust(max(1, width - 1)), max(1, width - 1)
        )
        stdscr.attroff(curses.A_REVERSE)

        prompt = f"> {self.input_buffer}"
        if len(prompt) >= width:
            prompt = prompt[-(width - 1) :]
        stdscr.addnstr(height - 1, 0, prompt, max(1, width - 1))
        stdscr.move(height - 1, min(len(prompt), max(0, width - 1)))
        stdscr.refresh()

    def _wrap_entries(self, width: int) -> List[str]:
        lines: List[str] = []
        for role, text in self.entries:
            prefix = f"[{role}] "
            body_width = max(10, width - len(prefix))
            paragraphs = text.splitlines() or [""]
            first_line = True

            for paragraph in paragraphs:
                wrapped = textwrap.wrap(paragraph, body_width) or [""]
                for segment in wrapped:
                    label = prefix if first_line else " " * len(prefix)
                    lines.append(f"{label}{segment}")
                    first_line = False

        return lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Claude Agent SDK recipe assistant for Trader Joe's"
    )
    parser.add_argument(
        "--store", default="226", help="Trader Joe's store code (default: 226)"
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Claude model name")
    return parser.parse_args()


def main():
    args = parse_args()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    agent = ClaudeRecipeAgent(api_key=api_key, model=args.model, store_code=args.store)
    try:
        curses.wrapper(RecipeAgentTUI(agent).run)
    finally:
        agent.close()


if __name__ == "__main__":
    main()
