"""MCP client: connects to MCP servers and wraps their tools as native nanobot tools."""

import os
import shutil
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry

# Whitelist of allowed MCP server commands for security
# Only these base commands are permitted to prevent arbitrary code execution
ALLOWED_MCP_COMMANDS = {
    "node",
    "python",
    "python3",
    "npx",
    "uvx",
}


def _validate_mcp_command(command: str) -> tuple[bool, str]:
    """
    Validate MCP server command for security.

    Only whitelisted commands are allowed to prevent command injection.

    Returns:
        (is_valid, error_message) tuple
    """
    if not command:
        return False, "Command cannot be empty"

    # Extract base command (handle paths)
    base_cmd = Path(command).name

    # Check against whitelist
    if base_cmd not in ALLOWED_MCP_COMMANDS:
        return False, (
            f"Command '{base_cmd}' not in allowed list: {', '.join(sorted(ALLOWED_MCP_COMMANDS))}. "
            "Only whitelisted commands can be used for MCP servers."
        )

    # If command is a path, verify it exists
    if os.path.sep in command:
        if not os.path.isfile(command):
            return False, f"Command path does not exist: {command}"
    else:
        # Verify command is in PATH
        if not shutil.which(command):
            return False, f"Command '{command}' not found in PATH"

    return True, ""


class MCPToolWrapper(Tool):
    """Wraps a single MCP server tool as a nanobot Tool."""

    def __init__(self, session, server_name: str, tool_def):
        self._session = session
        self._original_name = tool_def.name
        self._name = f"mcp_{server_name}_{tool_def.name}"
        self._description = tool_def.description or tool_def.name
        self._parameters = tool_def.inputSchema or {"type": "object", "properties": {}}

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        from mcp import types
        result = await self._session.call_tool(self._original_name, arguments=kwargs)
        parts = []
        for block in result.content:
            if isinstance(block, types.TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts) or "(no output)"


async def connect_mcp_servers(
    mcp_servers: dict, registry: ToolRegistry, stack: AsyncExitStack
) -> None:
    """Connect to configured MCP servers and register their tools."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    for name, cfg in mcp_servers.items():
        try:
            if cfg.command:
                # Validate command for security
                is_valid, error_msg = _validate_mcp_command(cfg.command)
                if not is_valid:
                    logger.error(
                        f"MCP server '{name}': command validation failed: {error_msg}"
                    )
                    continue

                params = StdioServerParameters(
                    command=cfg.command, args=cfg.args, env=cfg.env or None
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            elif cfg.url:
                from mcp.client.streamable_http import streamable_http_client
                read, write, _ = await stack.enter_async_context(
                    streamable_http_client(cfg.url)
                )
            else:
                logger.warning(f"MCP server '{name}': no command or url configured, skipping")
                continue

            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            tools = await session.list_tools()
            for tool_def in tools.tools:
                wrapper = MCPToolWrapper(session, name, tool_def)
                registry.register(wrapper)
                logger.debug(f"MCP: registered tool '{wrapper.name}' from server '{name}'")

            logger.info(f"MCP server '{name}': connected, {len(tools.tools)} tools registered")
        except Exception as e:
            logger.error(f"MCP server '{name}': failed to connect: {e}")
