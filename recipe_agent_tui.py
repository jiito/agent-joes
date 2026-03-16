#!/usr/bin/env python3
"""
Minimal Anthropic-powered recipe agent with a curses TUI.
"""

import argparse
import curses
import json
import os
import textwrap
from typing import Any, Dict, List, Tuple

from traderjoes import TraderJoesAPI

import anthropic
from braintrust import init_logger, wrap_anthropic
import dotenv


dotenv.load_dotenv()

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
MAX_TOOL_RESULTS = 8
BRAINTRUST_PROJECT = os.getenv("BRAINTRUST_PROJECT", "Trader Joes Recipe Agent")


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


class RecipeAgent:
    def __init__(self, api_key: str, model: str, store_code: str):
        if anthropic is None:
            raise RuntimeError(
                "Missing dependency: install the 'anthropic' package to run the recipe agent."
            )
        if init_logger is None or wrap_anthropic is None:
            raise RuntimeError(
                "Missing dependency: install the 'braintrust' package to enable Anthropic tracing."
            )

        self.api_key = api_key
        self.model = model
        self.store_code = store_code
        self.catalog_api = TraderJoesAPI(verbose=False)
        self.messages: List[Dict[str, Any]] = []
        self.logger = None
        if os.getenv("BRAINTRUST_API_KEY"):
            self.logger = init_logger(project=BRAINTRUST_PROJECT)
        self.client = wrap_anthropic(anthropic.Anthropic(api_key=api_key))

    def reset(self):
        self.messages = []

    def set_store_code(self, store_code: str):
        self.store_code = store_code

    def run_turn(self, user_text: str) -> Tuple[str, List[str]]:
        self.messages.append({"role": "user", "content": user_text})
        tool_events: List[str] = []

        while True:
            response = self._call_anthropic()
            content = response.get("content", [])
            self.messages.append({"role": "assistant", "content": content})

            tool_uses = [block for block in content if block.get("type") == "tool_use"]
            if tool_uses:
                tool_results = []
                for tool_use in tool_uses:
                    result, summary = self._execute_tool(
                        tool_use["name"], tool_use.get("input", {})
                    )
                    tool_events.append(summary)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use["id"],
                            "content": json.dumps(result, ensure_ascii=True),
                        }
                    )

                self.messages.append({"role": "user", "content": tool_results})
                continue

            text_blocks = [
                block.get("text", "").strip()
                for block in content
                if block.get("type") == "text" and block.get("text", "").strip()
            ]
            final_text = "\n\n".join(text_blocks).strip()
            return final_text or "No response returned.", tool_events

    def _call_anthropic(self) -> Dict[str, Any]:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1400,
                system=self._system_prompt(),
                messages=self.messages,
                tools=self._tool_definitions(),
            )
        except Exception as exc:
            raise RuntimeError(f"Anthropic API request failed: {exc}") from exc

        return {
            "content": [serialize_block(block) for block in response.content],
            "id": getattr(response, "id", None),
            "model": getattr(response, "model", None),
            "stop_reason": getattr(response, "stop_reason", None),
        }

    def _system_prompt(self) -> str:
        return (
            "You are a pragmatic recipe-planning assistant. "
            "Use Trader Joe's catalog tools to ground ingredient suggestions in real products when that would help. "
            f"The default store code is {self.store_code}. "
            "Do not invent exact SKUs or prices without tool confirmation. "
            "If the user asks for a recipe, produce a recipe title, a short why-this-works note, "
            "an ingredient list that references Trader Joe's product matches when available, "
            "and concise cooking steps. "
            "If product data is incomplete, say what is confirmed versus inferred. "
            "Use tools before making product-specific claims."
        )

    def _tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "search_products",
                "description": "Search Trader Joe's products by keyword for a store.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "search_term": {
                            "type": "string",
                            "description": "Ingredient or product phrase to search for.",
                        },
                        "store_code": {
                            "type": "string",
                            "description": "Trader Joe's store code. Omit to use the current default store.",
                        },
                    },
                    "required": ["search_term"],
                },
            },
            {
                "name": "lookup_skus",
                "description": "Look up specific Trader Joe's SKUs for the current or provided store.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "skus": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "One or more SKU identifiers.",
                        },
                        "store_code": {
                            "type": "string",
                            "description": "Trader Joe's store code. Omit to use the current default store.",
                        },
                    },
                    "required": ["skus"],
                },
            },
        ]

    def _execute_tool(
        self, name: str, payload: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], str]:
        if name == "search_products":
            search_term = str(payload.get("search_term", "")).strip()
            if not search_term:
                return {
                    "error": "search_term is required"
                }, "search_products failed: missing search term"

            store_code = str(payload.get("store_code") or self.store_code)
            result = self.catalog_api.search_products(store_code, search_term) or {}
            items = result.get("data", {}).get("products", {}).get("items", [])
            normalized = [normalize_product(item) for item in items[:MAX_TOOL_RESULTS]]
            summary = f"search_products('{search_term}', store={store_code}) -> {len(items)} result(s)"
            return {
                "store_code": store_code,
                "search_term": search_term,
                "total_results": len(items),
                "items": normalized,
            }, summary

        if name == "lookup_skus":
            raw_skus = payload.get("skus", [])
            skus = [str(sku).strip() for sku in raw_skus if str(sku).strip()]
            if not skus:
                return {
                    "error": "at least one SKU is required"
                }, "lookup_skus failed: missing SKUs"

            store_code = str(payload.get("store_code") or self.store_code)
            result = self.catalog_api.get_products_by_skus(store_code, skus) or {}
            items = result.get("data", {}).get("products", {}).get("items", [])
            normalized = [normalize_product(item) for item in items[:MAX_TOOL_RESULTS]]
            summary = f"lookup_skus({', '.join(skus)}, store={store_code}) -> {len(items)} result(s)"
            return {
                "store_code": store_code,
                "skus": skus,
                "total_results": len(items),
                "items": normalized,
            }, summary

        return {"error": f"unknown tool '{name}'"}, f"{name} failed: unknown tool"


def serialize_block(block: Any) -> Dict[str, Any]:
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json", exclude_none=True)
    if hasattr(block, "__dict__"):
        return {key: value for key, value in vars(block).items() if value is not None}
    raise TypeError(f"Unsupported Anthropic content block: {type(block)!r}")


class RecipeAgentTUI:
    def __init__(self, agent: RecipeAgent):
        self.agent = agent
        self.entries: List[Tuple[str, str]] = [
            (
                "System",
                "Enter a recipe request. Commands: /help, /clear, /quit, /store <code>.",
            )
        ]
        self.input_buffer = ""
        self.status = self._status_text()

    def run(self, stdscr):
        curses.curs_set(1)
        stdscr.keypad(True)

        while True:
            self._render(stdscr)
            key = stdscr.get_wch()

            if key == curses.KEY_RESIZE:
                continue

            if key in ("\n", "\r"):
                if not self._submit(stdscr):
                    return
                continue

            if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                self.input_buffer = self.input_buffer[:-1]
                continue

            if isinstance(key, str) and key.isprintable():
                self.input_buffer += key

    def _submit(self, stdscr) -> bool:
        text = self.input_buffer.strip()
        self.input_buffer = ""
        if not text:
            return True

        if text.startswith("/"):
            return self._handle_command(text)

        self.entries.append(("You", text))
        self.status = "Waiting on Anthropic..."
        self._render(stdscr)

        try:
            reply, tool_events = self.agent.run_turn(text)
            for event in tool_events:
                self.entries.append(("Tool", event))
            self.entries.append(("Chef", reply))
            self.status = self._status_text()
        except Exception as exc:
            self.entries.append(("Error", str(exc)))
            self.status = self._status_text()

        return True

    def _handle_command(self, text: str) -> bool:
        command, _, argument = text.partition(" ")
        command = command.lower()
        argument = argument.strip()

        if command in {"/quit", "/exit"}:
            return False

        if command in {"/clear", "/reset"}:
            self.agent.reset()
            self.entries = [
                (
                    "System",
                    "Conversation cleared. Commands: /help, /clear, /quit, /store <code>.",
                )
            ]
            self.status = self._status_text()
            return True

        if command == "/store":
            if not argument:
                self.entries.append(("System", "Usage: /store <code>"))
                return True
            self.agent.set_store_code(argument)
            self.entries.append(("System", f"Default store changed to {argument}."))
            self.status = self._status_text()
            return True

        if command == "/help":
            self.entries.append(
                (
                    "System",
                    "Ask for recipes, substitutions, meal ideas, or shopping help. "
                    "Use /store <code> to change stores, /clear to reset the chat, and /quit to exit.",
                )
            )
            return True

        self.entries.append(("System", f"Unknown command: {command}"))
        return True

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
        description="Anthropic recipe agent for Trader Joe's"
    )
    parser.add_argument(
        "--store", default="226", help="Trader Joe's store code (default: 226)"
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Anthropic model name")
    return parser.parse_args()


def main():
    args = parse_args()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is required")

    agent = RecipeAgent(api_key=api_key, model=args.model, store_code=args.store)
    tui = RecipeAgentTUI(agent)
    curses.wrapper(tui.run)


if __name__ == "__main__":
    main()
