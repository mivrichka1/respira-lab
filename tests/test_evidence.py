import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from respira import assistant, web
from respira.gateway import Outcome
from respira.assistant import query_arguments
from respira.scenarios import build_scenario


def test_case_query_allows_only_pubmed_terms():
    assert query_arguments(
        '```json\n{"condition":" COPD ","focus":"pulmonary rehabilitation","maxResults":1000}\n```'
    ) == {"query": "COPD pulmonary rehabilitation", "maxResults": 4, "summaryCount": 4, "hasAbstract": True}
    with pytest.raises(ValueError):
        query_arguments('{"condition":"","focus":""}')


def test_search_by_edited_case_uses_mcp_with_prepared_args(monkeypatch):
    arguments = {"query": "COPD", "maxResults": 4, "summaryCount": 4, "hasAbstract": True}
    planner = AsyncMock(return_value=(arguments, None))
    call = AsyncMock(return_value=SimpleNamespace(
        error=None, serialise=lambda: {"result": {"summaries": [{"pmid": "12345678"}]}},
    ))
    monkeypatch.setattr(web, "prepare_case_query", planner)
    monkeypatch.setattr(web.gateway, "call", call)
    response = TestClient(web.app).post("/api/evidence", json={
        "scenario": "hypoxemia", "description": "ХОБЛ и легочная реабилитация",
    })
    assert response.status_code == 200 and response.json()["error"] is None
    planner.assert_awaited_once_with("ХОБЛ и легочная реабилитация")
    call.assert_awaited_once_with("pubmed", "pubmed_search_articles", arguments)


def test_default_case_can_use_preset_and_agent_receives_listing(monkeypatch):
    planner = AsyncMock()
    outcome = SimpleNamespace(error=None, serialise=lambda: {"result": {"summaries": []}})
    monkeypatch.setattr(web, "prepare_case_query", planner)
    monkeypatch.setattr(web.gateway, "call", AsyncMock(return_value=outcome))
    client = TestClient(web.app)
    profile = build_scenario()
    response = client.post("/api/evidence", json={
        "scenario": profile["id"], "description": profile["description"],
    })
    assert response.json()["error"] is None
    planner.assert_not_called()
    agent = AsyncMock(return_value={"type": "done", "text": "готово"})
    monkeypatch.setattr(web, "reply_to", agent)
    pick = {"pmid": "12345678", "title": "Example"}
    response = client.post("/api/agent", json={
        "messages": [{"role": "user", "content": "Открой первую запись"}],
        "description": profile["description"], "articles": [pick],
        "calculations": [{"tool": "pf_ratio", "value": 200, "unit": "мм рт. ст."}],
    })
    assert response.status_code == 200 and "готово" in response.text
    assert agent.await_args.kwargs["articles"] == [pick]
    assert agent.await_args.kwargs["calculations"][0]["value"] == 200


def test_agent_uses_pubmed_abstract_in_followup(monkeypatch):
    monkeypatch.setenv("ROUTERAI_API_KEY", "test-only")
    pmid = "12345678"
    tool = SimpleNamespace(name="pubmed_fetch_articles", title="Fetch", description="", input_schema={"type": "object"})
    function_call = SimpleNamespace(
        id="call_1", type="function",
        function=SimpleNamespace(name="pubmed__pubmed_fetch_articles", arguments='{"pmids":["12345678"]}'),
        model_dump=lambda **_: {"id": "call_1"},
    )
    first = SimpleNamespace(content=None, tool_calls=[function_call], model_extra={})
    last = SimpleNamespace(content="Готово, разобрал аннотацию.", tool_calls=[])
    final_context = []

    async def complete(**options):
        if options["messages"][-1]["role"] != "tool":
            return SimpleNamespace(choices=[SimpleNamespace(message=first)])
        final_context.append(options["messages"][-1]["content"])
        return SimpleNamespace(choices=[SimpleNamespace(message=last)])

    @asynccontextmanager
    async def fake_router(*_):
        yield SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete)))

    async def discover(source):
        return ([tool] if source == "pubmed" else []), None

    outcome = Outcome("pubmed", tool.name, {"pmids": [pmid]}, result={
        "articles": [{"pmid": pmid, "abstractText": "Abstract from PubMed."}],
    })
    gateway = SimpleNamespace(discover=discover, call=AsyncMock(return_value=outcome))
    monkeypatch.setattr(assistant, "router_client", fake_router)
    events = []
    response = asyncio.run(assistant.reply_to(
        gateway, [{"role": "user", "content": "Разбери вторую статью."}], {}, False, events.append,
        articles=[{"pmid": "11111111", "title": "First"}, {"pmid": pmid, "title": "Second"}],
    ))
    assert response == {"type": "done", "text": last.content}
    gateway.call.assert_awaited_once_with("pubmed", tool.name, {"pmids": [pmid]}, teaching_case=False, tool=tool)
    assert [event["type"] for event in events] == ["tool_start", "tool"]
    assert "Abstract from PubMed." in final_context[0]


def test_compact_agent_schema_preserves_pubmed_filters():
    tool = SimpleNamespace(name="pubmed_search_articles", description="Verbose tool description", input_schema={
        "type": "object", "additionalProperties": False,
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {
            "query": {"type": "string", "title": "Query", "description": "Verbose query description"},
            "dateRange": {
                "type": "object", "required": ["minDate", "maxDate"],
                "properties": {
                    "minDate": {"type": "string", "pattern": r"^\d{4}$"},
                    "maxDate": {"type": "string", "pattern": r"^\d{4}$"},
                    "dateType": {"enum": ["pdat", "edat"], "default": "pdat"},
                },
            },
        },
    })
    definition = assistant.model_tool("pubmed", tool)["function"]
    compact = definition["parameters"]
    assert definition["name"] == "pubmed__pubmed_search_articles"
    assert "title" not in compact["properties"]["query"]
    assert tool.input_schema["properties"]["query"]["description"] == "Verbose query description"
    assert compact["properties"]["dateRange"]["properties"]["dateType"]["default"] == "pdat"
    accepted = {"query": "COPD", "dateRange": {"minDate": "2022", "maxDate": "2025", "dateType": "pdat"}}
    rejected = {"query": "COPD", "dateRange": {"minDate": "2022"}}
    assert Draft202012Validator(compact).is_valid(accepted)
    assert not Draft202012Validator(compact).is_valid(rejected)
