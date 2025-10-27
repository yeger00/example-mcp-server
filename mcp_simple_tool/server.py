import anyio
import click
import mcp.types as types
from mcp.server.lowlevel import Server
from .cisa_vuln_checker import check_cve_exists, get_recent_cves


@click.command()
@click.option("--port", default=8000, help="Port to listen on for SSE")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="Transport type",
)
def main(port: int, transport: str) -> int:
    app = Server("mcp-website-fetcher")

    mood_description: str = (
        "Ask this MCP server about its mood! You can phrase your question "
        "in any way you like - 'How are you?', 'What's your mood?', or even "
        "'Are you having a good day?'. The server will always respond with "
        "a cheerful message and a heart ❤️"
    )

    @app.call_tool()
    async def fetch_tool( # type: ignore[unused-function]
        name: str, arguments: dict
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if name == "get_recent_cves":
            if "days" not in arguments:
                return [types.TextContent(
                    type="text",
                    text="Error: Missing required argument 'days'"
                )]
            return await get_recent_cves(arguments["days"])
        elif name == "check_cve_exists":
            if "cve_id" not in arguments:
                return [types.TextContent(
                    type="text",
                    text="Error: Missing required argument 'cve_id'"
                )]
            return await check_cve_exists(arguments["cve_id"])
        else:
            return [types.TextContent(
                type="text",
                text=f"Error: Unknown tool: {name}"
            )]

    @app.list_tools()
    async def list_tools() -> list[types.Tool]: # type: ignore[unused-function]
        return [
            types.Tool(
                name="get_recent_cves",
                description="Get all CVEs added in the last X days.",
                inputSchema={
                    "type": "object",
                    "required": ["days"],
                    "properties": {
                        "days": {
                            "type": "int",
                            "description": "Number of days to look back",
                        }
                    },
                },
            ),
            types.Tool(
                name="check_cve_exists",
                description="Check if a given CVE exists in the list and return its details.",
                inputSchema={
                    "type": "object",
                    "required": ["cve_id"],
                    "properties": {
                        "cve_id": {
                            "type": "string",
                            "description": "The CVE ID to check (e.g., 'CVE-2023-1234')",
                        }
                    },
                },
            )
        ]

    if transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        from starlette.middleware import Middleware
        from starlette.middleware.cors import CORSMiddleware

        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await app.run(
                    streams[0], streams[1], app.create_initialization_options()
                )

        starlette_app = Starlette(
            debug=True,
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )

        # Taken from: https://github.com/jlowin/fastmcp/issues/840#issuecomment-3381053306
        starlette_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Allows all origins
            allow_credentials=True,
            allow_methods=["*"],  # Allows all methods
            allow_headers=["*"],  # Allows all headers
        )

        import uvicorn

        uvicorn.run(starlette_app, host="0.0.0.0", port=port)
    else:
        from mcp.server.stdio import stdio_server

        async def arun():
            async with stdio_server() as streams:
                await app.run(
                    streams[0], streams[1], app.create_initialization_options()
                )

        anyio.run(arun)

    return 0
