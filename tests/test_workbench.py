import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mcp import Client, StdioServerParameters

from respira.gateway import Gateway, sanitise
from respira.scales import EXAMPLE, news2


def test_stdio_catalog_calculators_and_transport():
    async def run():
        gateway = Gateway()
        tools, error = await gateway.discover("stdio")
        assert not error
        assert {tool.name for tool in tools} == {"pf_ratio", "qsofa", "curb65", "list_calculators"}
        cases = [
            ("pf_ratio", {"pao2": 80, "fio2": .4}, 200),
            ("qsofa", {"resp_rate": 24, "systolic": 100, "altered_mentation": False}, 2),
            ("curb65", {"confusion": False, "urea": 7, "resp_rate": 30, "systolic": 90,
                        "diastolic": 60, "age": 65}, 3),
        ]
        for name, arguments, expected in cases:
            call = (await gateway.call("stdio", name, arguments)).serialise()
            assert call["error"] is None and call["result"]["value"] == expected
            assert call["request"]["method"] == "tools/call"
            assert call["request"]["id"] == call["response"]["id"]
            assert any(item["packet"].get("method") == "initialize" for item in call["trace"])
        catalog = await gateway.call("stdio", "list_calculators", {})
        assert len(catalog.result["calculators"]) == 3
        fields = catalog.result["calculators"][0]["parameters"]["properties"]
        assert (fields["pao2"]["minimum"], fields["pao2"]["unit"]) == (10, "мм рт. ст.")

    asyncio.run(run())


def test_stdio_rejects_numeric_strings_at_server():
    async def run():
        config = StdioServerParameters(command=sys.executable, args=["-m", "respira.server"])
        async with Client(config, mode="legacy") as client:
            result = await client.call_tool("pf_ratio", {"pao2": "80", "fio2": .4})
        assert result.is_error

    asyncio.run(run())


def test_news2_scale_bands_and_oxygen():
    fields = ("resp_rate", "spo2", "spo2_scale", "supplemental_oxygen", "systolic", "pulse", "consciousness", "temp")
    inputs = {key: EXAMPLE[key] for key in fields}
    assert news2(**inputs)["value"] == 7
    assert news2(**(inputs | {"spo2_scale": "2", "spo2": 95}))["components"]["SpO₂ · шкала 2"] == 2
    assert news2(**(inputs | {"spo2_scale": "2", "spo2": 95, "supplemental_oxygen": False}))["components"]["SpO₂ · шкала 2"] == 0


def test_smart_defaults_apply_only_to_teaching_fields():
    schema = {"properties": {"fio2": {"type": "number"}, "spo2": {"type": "integer"},
                             "supplemental_oxygen": {"type": "boolean"}},
              "required": ["fio2", "spo2", "supplemental_oxygen"]}
    arguments = {"fio2": "0,4", "supplemental_oxygen": "false"}
    assert sanitise(arguments, schema) == ({"fio2": .4, "supplemental_oxygen": False}, [])
    assert sanitise(arguments, schema, teaching_case=True) == (
        {"fio2": .4, "supplemental_oxygen": False, "spo2": 94}, ["spo2"],
    )


def test_pubmed_deadline(monkeypatch):
    from contextlib import asynccontextmanager

    class UnresponsiveGateway(Gateway):
        @asynccontextmanager
        async def transport(self, source):
            await asyncio.sleep(5)
            yield

    monkeypatch.setattr("respira.gateway.PUBMED_TIMEOUT", .05)
    tools, error = asyncio.run(UnresponsiveGateway().discover("pubmed"))
    assert tools == []
    assert "вовремя" in error



def test_pubmed_cache_skips_second_transport(monkeypatch):
    async def run():
        gateway = Gateway()
        tool = SimpleNamespace(input_schema={"type": "object"})
        execute = AsyncMock(return_value=SimpleNamespace(
            is_error=False, structured_content={"summaries": [{"pmid": "12345678"}]},
        ))
        monkeypatch.setattr(gateway, "execute", execute)
        args = {"query": "hypoxemia"}
        first = await gateway.call("pubmed", "pubmed_search_articles", args, tool=tool)
        second = await gateway.call("pubmed", "pubmed_search_articles", args, tool=tool)
        assert not first.cached and second.cached
        assert first.result == second.result
        assert second.trace == []
        execute.assert_awaited_once()

    asyncio.run(run())


@pytest.mark.skipif(os.getenv("RESPIRA_LIVE_PUBMED") != "1", reason="live PubMed requires Internet")
def test_live_pubmed_search_and_abstract():
    async def run():
        gateway = Gateway()
        result = await gateway.call("pubmed", "pubmed_search_articles", {
            "query": "COPD pulmonary rehabilitation", "maxResults": 3, "summaryCount": 3, "hasAbstract": True,
        })
        assert not result.error, result.error
        articles = result.result["summaries"]
        assert len(articles) == 3 and articles[0]["title"]
        pmid = articles[0]["pmid"]
        entry = await gateway.call("pubmed", "pubmed_fetch_articles", {"pmids": [pmid], "includeMesh": False})
        assert not entry.error, entry.error
        article = entry.result["articles"][0]
        assert article["pmid"] == pmid and article["abstractText"]
        assert entry.serialise()["request"]["id"] == entry.serialise()["response"]["id"]

    asyncio.run(run())
