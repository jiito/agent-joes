#!/usr/bin/env python3
"""
Request-scoped recipe agent for webhook and server use.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from anthropic import Anthropic

from traderjoes import TraderJoesAPI

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
DEFAULT_STORE_CODE = os.getenv("DEFAULT_STORE_CODE", "226")
MAX_TOOL_RESULTS = 8
MAX_TOOL_ROUNDS = 4
MAX_SMS_CHARS = 1200


def normalize_product(item: dict[str, Any]) -> dict[str, Any]:
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


def build_system_prompt(store_code: str) -> str:
    return (
        "You are a pragmatic Trader Joe's recipe-planning assistant responding over SMS. "
        "Use Trader Joe's catalog tools to ground ingredient suggestions in real products when helpful. "
        f"The default store code is {store_code}. "
        "Do not invent exact SKUs or prices without tool confirmation. "
        "When the user asks for a recipe, produce a recipe title, a short why-this-works note, "
        "a concise ingredient list that references Trader Joe's product matches when available, "
        "and brief cooking steps. "
        "If product data is incomplete, clearly separate confirmed details from inference. "
        "Keep the final answer compact and plain text for SMS."
    )


def build_tools() -> list[dict[str, Any]]:
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
                        "description": "Store code; omit to use the default store.",
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
                        "description": "Store code; omit to use the default store.",
                    },
                },
                "required": ["skus"],
            },
        },
    ]


def _serialize_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True)


def _truncate_for_sms(text: str, limit: int = MAX_SMS_CHARS) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 3].rstrip() + "..."


class TraderJoesRecipeAgent:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, store_code: str = DEFAULT_STORE_CODE):
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required")

        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.store_code = store_code
        self.catalog_api = TraderJoesAPI(verbose=False)
        self.tools = build_tools()
        self.tool_handlers: dict[str, Callable[[dict[str, Any]], str]] = {
            "search_products": self._search_products,
            "lookup_skus": self._lookup_skus,
        }

    def _search_products(self, args: dict[str, Any]) -> str:
        term = str(args.get("search_term", "")).strip()
        if not term:
            raise ValueError("search_term is required")

        code = str(args.get("store_code") or self.store_code)
        result = self.catalog_api.search_products(code, term) or {}
        items = result.get("data", {}).get("products", {}).get("items", [])
        normalized = [normalize_product(item) for item in items[:MAX_TOOL_RESULTS]]
        return _serialize_result(
            {
                "store_code": code,
                "search_term": term,
                "total_results": len(items),
                "items": normalized,
            }
        )

    def _lookup_skus(self, args: dict[str, Any]) -> str:
        raw_skus = args.get("skus", [])
        skus = [str(sku).strip() for sku in raw_skus if str(sku).strip()]
        if not skus:
            raise ValueError("at least one SKU is required")

        code = str(args.get("store_code") or self.store_code)
        result = self.catalog_api.get_products_by_skus(code, skus) or {}
        items = result.get("data", {}).get("products", {}).get("items", [])
        normalized = [normalize_product(item) for item in items[:MAX_TOOL_RESULTS]]
        return _serialize_result(
            {
                "store_code": code,
                "skus": skus,
                "total_results": len(items),
                "items": normalized,
            }
        )

    def run(self, user_text: str) -> str:
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]

        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.messages.create(
                model=self.model,
                system=build_system_prompt(self.store_code),
                tools=self.tools,
                messages=messages,
                max_tokens=500,
                temperature=0.3,
            )

            assistant_blocks: list[dict[str, Any]] = []
            tool_results: list[dict[str, Any]] = []
            text_chunks: list[str] = []

            for block in response.content:
                if block.type == "text":
                    assistant_blocks.append({"type": "text", "text": block.text})
                    if block.text.strip():
                        text_chunks.append(block.text.strip())
                    continue

                if block.type != "tool_use":
                    continue

                assistant_blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

                handler = self.tool_handlers.get(block.name)
                if handler is None:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Unsupported tool: {block.name}",
                            "is_error": True,
                        }
                    )
                    continue

                try:
                    tool_output = handler(block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": tool_output,
                        }
                    )
                except Exception as exc:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(exc),
                            "is_error": True,
                        }
                    )

            if tool_results:
                messages.append({"role": "assistant", "content": assistant_blocks})
                messages.append({"role": "user", "content": tool_results})
                continue

            final_text = _truncate_for_sms("\n\n".join(text_chunks))
            if final_text:
                return final_text

            if response.stop_reason == "max_tokens":
                raise RuntimeError("The agent response was truncated before it completed.")

            raise RuntimeError("The agent returned no text.")

        raise RuntimeError("The agent exceeded the maximum number of tool rounds.")


def run_recipe_agent(user_text: str, store_code: str = DEFAULT_STORE_CODE, model: str = DEFAULT_MODEL) -> str:
    return TraderJoesRecipeAgent(
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        model=model,
        store_code=store_code,
    ).run(user_text)
