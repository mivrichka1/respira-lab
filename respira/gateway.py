"""Transport gateway shared by the workbench and agent."""

import asyncio
import json
import math
import os
import ssl
import sys
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import httpx2
import truststore
from jsonschema import Draft202012Validator
from mcp import Client, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.shared.message import SessionMessage
from mcp_types import CONNECTION_CLOSED, INTERNAL_ERROR, REQUEST_TIMEOUT

from respira.scales import EXAMPLE, METHODS

Source = Literal["stdio", "sse", "pubmed"]
SOURCES = {"stdio": "stdio", "sse": "SSE", "pubmed": "PubMed"}
PUBMED_URL = "https://pubmed.caseyjhand.com/mcp"
PUBMED_SEARCH = "pubmed_search_articles"
PUBMED_FETCH = "pubmed_fetch_articles"
PUBMED_TOOLS = {PUBMED_SEARCH, PUBMED_FETCH}
PUBMED_TIMEOUT = 12
CACHE_SECONDS = 600
ROOT = Path(__file__).resolve().parents[1]


class TraceStream:
    def __init__(self, stream, events, direction):
        self.stream = stream
        self.events = events
        self.direction = direction

    async def __aenter__(self):
        await self.stream.__aenter__()
        return self

    async def __aexit__(self, *exc):
        return await self.stream.__aexit__(*exc)

    def record(self, message):
        if isinstance(message, SessionMessage):
            self.events.append({
                "direction": self.direction,
                "packet": message.message.model_dump(mode="json", by_alias=True, exclude_unset=True),
            })

    async def send(self, message):
        self.record(message)
        await self.stream.send(message)

    async def __aiter__(self):
        async for message in self.stream:
            self.record(message)
            yield message


@asynccontextmanager
async def capture(transport, events):
    async with transport as (incoming, outgoing):
        yield TraceStream(incoming, events, "in"), TraceStream(outgoing, events, "out")


@dataclass
class Outcome:
    source: Source
    tool: str
    arguments: dict
    result: object = None
    error: str | None = None
    defaults: list[str] = field(default_factory=list)
    cached: bool = False
    trace: list = field(default_factory=list)

    def serialise(self):
        data = asdict(self)
        for index in range(len(self.trace) - 1, -1, -1):
            event = self.trace[index]
            request = event["packet"]
            if event["direction"] == "out" and request.get("method") == "tools/call":
                data["request"] = request
                data["response"] = next(
                    (e["packet"] for e in self.trace[index + 1:]
                     if e["direction"] == "in" and e["packet"].get("id") == request["id"]
                     and ("result" in e["packet"] or "error" in e["packet"])), None,
                )
                break
        return data


def errors_inside(error):
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            yield from errors_inside(child)
    else:
        yield error


def retryable(error):
    return any(isinstance(e, (OSError, TimeoutError, httpx2.TransportError))
               or isinstance(e, MCPError) and e.error.code in {CONNECTION_CLOSED, REQUEST_TIMEOUT, INTERNAL_ERROR}
               for e in errors_inside(error))


def describe_error(error):
    causes = tuple(errors_inside(error))
    if any(isinstance(e, (TimeoutError, httpx2.TimeoutException))
           or isinstance(e, MCPError) and e.error.code == REQUEST_TIMEOUT for e in causes):
        return "Источник не ответил вовремя. Повторите запрос."
    for cause in causes:
        if isinstance(cause, httpx2.HTTPStatusError) and cause.response.status_code == 429:
            return "Источник ограничил частоту запросов. Повторите позже."
    if retryable(error):
        return "MCP-источник временно недоступен. Повторите запрос."
    return "Не удалось завершить обмен с MCP-сервером."


def sanitise(arguments, schema, *, teaching_case=False):
    values = dict(arguments)
    defaults = []
    properties = schema.get("properties", {})
    if teaching_case:
        for name in schema.get("required", []):
            if name in EXAMPLE and (name not in values or values[name] is None or values[name] == ""):
                values[name] = EXAMPLE[name]
                defaults.append(name)

    for name, definition in properties.items():
        value = values.get(name)
        if not isinstance(value, str):
            continue
        kind = definition.get("type")
        normal = value.strip().replace(",", ".")
        try:
            if kind == "integer":
                values[name] = int(normal)
            elif kind == "number" and math.isfinite(float(normal)):
                values[name] = float(normal)
            elif kind == "boolean" and normal.casefold() in {"true", "false"}:
                values[name] = normal.casefold() == "true"
        except ValueError:
            pass
    return values, defaults


def validate(values, schema):
    if any(isinstance(value, float) and not math.isfinite(value) for value in values.values()):
        return "Число должно быть конечным."
    issue = next(Draft202012Validator(schema).iter_errors(values), None)
    if issue is None:
        return None
    if issue.validator == "required":
        required = [name for name in issue.validator_value if name not in values]
        titles = [schema.get("properties", {}).get(name, {}).get("title", name) for name in required]
        return "Заполните обязательные поля: " + ", ".join(titles) + "."
    label = issue.schema.get("title") or ".".join(map(str, issue.path)) or "Параметры"
    if issue.validator in {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"}:
        return f"{label}: проверьте допустимую границу {issue.validator_value}."
    return f"{label}: проверьте тип или выберите допустимое значение."


def unpack(reply):
    if reply.structured_content is not None:
        return reply.structured_content
    blocks = reply.content
    if len(blocks) == 1 and blocks[0].type == "text":
        try:
            return json.loads(blocks[0].text)
        except json.JSONDecodeError:
            return blocks[0].text
    return [block.model_dump(mode="json") for block in blocks]


class Gateway:
    def __init__(self):
        self.sse_url = os.getenv("RESPIRA_SSE_URL", "http://127.0.0.1:8002/sse")
        self.pubmed_url = os.getenv("RESPIRA_PUBMED_URL", PUBMED_URL)
        self.catalog = {}
        self.cache = OrderedDict()

    @asynccontextmanager
    async def transport(self, source):
        if source == "stdio":
            config = StdioServerParameters(command=sys.executable, args=["-m", "respira.server"], cwd=ROOT)
            async with stdio_client(config) as streams:
                yield streams
        elif source == "sse":
            async with sse_client(self.sse_url, timeout=2, sse_read_timeout=5) as streams:
                yield streams
        else:
            verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            async with httpx2.AsyncClient(verify=verify, timeout=httpx2.Timeout(4, connect=2.5)) as http:
                async with streamable_http_client(self.pubmed_url, http_client=http) as streams:
                    yield streams

    async def execute(self, source, operation, events):
        attempts = {"stdio": 1, "sse": 3, "pubmed": 2}[source]
        async with asyncio.timeout(PUBMED_TIMEOUT if source == "pubmed" else 8):
            for attempt in range(attempts):
                connected = False
                try:
                    budget = PUBMED_TIMEOUT / 2 if source == "pubmed" and attempt == 0 else None
                    async with asyncio.timeout(budget):
                        transport = capture(self.transport(source), events)
                        async with Client(transport, mode="legacy", cache=None) as client:
                            connected = True
                            return await operation(client)
                except Exception as error:
                    if attempt + 1 == attempts or not retryable(error) or (connected and source != "pubmed"):
                        raise
                    await asyncio.sleep(.2 * (2**attempt))

    async def discover(self, source):
        entry = self.catalog.get(source)
        if entry and entry[0] > time.monotonic():
            return entry[1], None
        try:
            listing = await self.execute(source, lambda c: c.list_tools(), [])
        except Exception as error:
            return [], describe_error(error)
        tools = [t for t in listing.tools if source != "pubmed" or t.name in PUBMED_TOOLS]
        self.catalog[source] = (time.monotonic() + 90, tools)
        return tools, None

    async def call(self, source, name, arguments, *, teaching_case=False, tool=None):
        outcome = Outcome(source, name, arguments)
        try:
            async with asyncio.timeout(PUBMED_TIMEOUT if source == "pubmed" else None):
                return await self.complete_call(outcome, teaching_case=teaching_case, tool=tool)
        except TimeoutError:
            outcome.error = describe_error(TimeoutError())
            return outcome

    async def complete_call(self, outcome, *, teaching_case, tool):
        source, name, arguments = outcome.source, outcome.tool, outcome.arguments
        if tool is None:
            listing, error = await self.discover(source)
            if error:
                outcome.error = error
                return outcome
            tool = next((t for t in listing if t.name == name), None)
        if tool is None:
            outcome.error = "Инструмент недоступен в выбранном источнике."
            return outcome

        schema = tool.input_schema
        if source == "sse":
            outcome.arguments, outcome.defaults = sanitise(
                arguments, schema, teaching_case=teaching_case and name in METHODS,
            )
        if source == "pubmed" and name == PUBMED_SEARCH:
            query = arguments.get("query")
            if not isinstance(query, str) or not query.strip():
                outcome.error = "Укажите поисковый запрос для PubMed."
                return outcome
        outcome.error = validate(outcome.arguments, schema)
        if outcome.error:
            return outcome

        key = (name, json.dumps(outcome.arguments, sort_keys=True, ensure_ascii=False))
        if source == "pubmed":
            entry = self.cache.get(key)
            if entry and entry[0] > time.monotonic():
                outcome.cached, outcome.result = True, entry[1]
                return outcome
        try:
            reply = await self.execute(source, lambda c: c.call_tool(name, outcome.arguments), outcome.trace)
        except Exception as error:
            outcome.error = describe_error(error)
            return outcome
        if reply.is_error:
            prefix = f"Error executing tool {name}: "
            texts = [block.text.removeprefix(prefix) for block in reply.content if block.type == "text"]
            outcome.error = " ".join(texts)[:700] or "Инструмент вернул ошибку."
            return outcome
        outcome.result = unpack(reply)
        if source == "pubmed":
            self.cache[key] = (time.monotonic() + CACHE_SECONDS, outcome.result)
            self.cache.move_to_end(key)
            if len(self.cache) > 128:
                self.cache.popitem(last=False)
        return outcome
