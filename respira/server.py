"""Entry point for the independent stdio and local SSE MCP services."""

import argparse
import logging
import sys

import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

from respira.scales import METHODS, SSE_SCALES, STDIO_SCALES


def make_server(source):
    server = MCPServer(f"Respira Lab {source}")
    scales = STDIO_SCALES if source == "stdio" else SSE_SCALES
    for scale in scales:
        server.add_tool(scale, title=METHODS[scale.__name__][0])

    @server.tool()
    async def list_calculators() -> dict:
        """Перечисляет шкалы, методики, источники, единицы и допустимые параметры."""
        tools = await server.list_tools()
        return {"calculators": [
            {"name": t.name, "title": t.title, "description": t.description,
             "specialty": METHODS[t.name][1], "source": METHODS[t.name][2],
             "parameters": t.input_schema}
            for t in tools if t.name in METHODS
        ]}

    return server


async def health(_request):
    return PlainTextResponse("ok")


class MessageEndpoint:
    """Also accept the slashless route printed in the assignment."""

    def __init__(self, handler):
        self.handler = handler

    async def __call__(self, scope, receive, send):
        await self.handler(scope, receive, send)


def make_sse_app(host):
    app = make_server("sse").sse_app(host=host)
    messages = next(route for route in app.routes if isinstance(route, Mount) and route.path == "/messages")
    app.routes.append(Route("/messages", MessageEndpoint(messages.app), methods=["POST"]))
    app.routes.append(Route("/health", health))
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("transport", choices=("stdio", "sse"), nargs="?", default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    if args.transport == "stdio":
        make_server("stdio").run()
    else:
        uvicorn.run(make_sse_app(args.host), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
