"""Single-origin API and static Vue app."""

import asyncio
import json
import logging
import os
from contextlib import suppress
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from respira.assistant import prepare_case_query, reply_to, search_arguments
from respira.gateway import PUBMED_SEARCH, Gateway, Source
from respira.scales import EXAMPLE, METHODS
from respira.scenarios import PROFILES, build_scenario, next_scenario

load_dotenv()
app = FastAPI(title="Respira Lab")
gateway = Gateway()
logger = logging.getLogger(__name__)


class ToolRequest(BaseModel):
    source: Source
    tool: str
    arguments: dict = Field(default_factory=dict)
    teaching_case: bool = False


class Message(BaseModel):
    role: Literal["assistant", "user"]
    content: str = Field(min_length=1, max_length=12000)


class EvidenceRequest(BaseModel):
    description: str = Field(min_length=1, max_length=2500)
    scenario: str | None = None


class ArticleContext(BaseModel):
    pmid: str = Field(pattern=r"^\d{1,12}$")
    title: str = Field(max_length=500)


class CalculationContext(BaseModel):
    tool: str = Field(max_length=40)
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(default="", max_length=80)


class AgentRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=16)
    case: dict = Field(default_factory=dict)
    description: str = Field(default="", max_length=2500)
    articles: list[ArticleContext] = Field(default_factory=list, max_length=8)
    calculations: list[CalculationContext] = Field(default_factory=list, max_length=6)
    teaching_case: bool = False


@app.get("/api/health")
async def health():
    return {"status": "ok", "agent": bool(os.getenv("ROUTERAI_API_KEY", "").strip())}


@app.get("/api/case")
async def case():
    return EXAMPLE



@app.get("/api/scenario")
async def scenario(previous: str | None = None):
    return next_scenario(previous) if previous else build_scenario()


@app.get("/api/tools/{source}")
async def tools(source: Source):
    listing, error = await gateway.discover(source)
    return {"error": error, "tools": [
        {"name": t.name, "title": t.title or t.name, "description": t.description,
         "schema": t.input_schema, "specialty": METHODS.get(t.name, ("", ""))[1]}
        for t in listing
    ]}


@app.post("/api/call")
async def call(request: ToolRequest):
    result = await gateway.call(request.source, request.tool, request.arguments,
                                teaching_case=request.teaching_case)
    return result.serialise()



@app.post("/api/evidence")
async def evidence(request: EvidenceRequest):
    description = request.description.strip()
    if not description:
        return {"error": "Опишите учебный случай."}
    profile = PROFILES.get(request.scenario or "")
    preset = profile.get("research") if profile and description == profile["description"] else None
    if preset:
        arguments = search_arguments(preset)
    else:
        arguments, error = await prepare_case_query(description)
        if error:
            return {"error": error}
    result = await gateway.call("pubmed", PUBMED_SEARCH, arguments)
    return {"call": result.serialise(), "error": result.error}


@app.post("/api/agent")
async def agent(request: AgentRequest):
    async def stream():
        events = asyncio.Queue()
        case_values = {name: value for name, value in request.case.items()
                       if name in EXAMPLE and isinstance(value, (int, float, bool, str))}

        async def run():
            try:
                async with asyncio.timeout(95):
                    response = await reply_to(gateway, [m.model_dump() for m in request.messages],
                                              case_values, request.teaching_case, events.put_nowait,
                                              description=request.description,
                                              articles=[item.model_dump() for item in request.articles],
                                              calculations=[item.model_dump() for item in request.calculations
                                                            if item.tool in METHODS])
            except TimeoutError:
                response = {"type": "done", "error": "Истекло время обработки запроса агентом."}
            except Exception:
                logger.exception("Agent request failed")
                response = {"type": "done", "error": "Не удалось завершить запрос агентом."}
            await events.put(response)

        worker = asyncio.create_task(run())
        try:
            while True:
                event = await events.get()
                yield json.dumps(event, ensure_ascii=False) + "\n"
                if event["type"] == "done":
                    break
        finally:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker

    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


asset_dir = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if asset_dir.is_dir():
    app.mount("/", StaticFiles(directory=asset_dir, html=True), name="ui")
