"""
IP Analyzer Agent - Claude with Bash Access

This agent is literally just Claude with access to network investigation tools.
Send any message and Claude autonomously investigates using dig, whois, etc.

Includes comprehensive logging, cost tracking, and event tracing.
"""

from agentuity import AgentRequest, AgentResponse, AgentContext
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    AssistantMessage,
    UserMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ResultMessage,
)
from datetime import datetime, timezone


async def run(request: AgentRequest, response: AgentResponse, context: AgentContext):
    """
    IP Analyzer Agent - Just pass user message to Claude with Bash access.

    Send anything:
    - "Investigate 181.196.28.68"
    - "Is 200.109.114.147 legit or spoofing?"
    - "Check if pmg.produccion.gob.ec is suspicious"

    Claude figures it out and investigates autonomously.
    """
    # Get user message
    try:
        user_message = await request.data.text()
    except Exception as e:
        context.logger.debug(f"Could not read text: {e}")
        user_message = ""

    if not user_message or user_message.strip() == "":
        return response.text(
            "Hi! I'm an IP investigation agent powered by Claude.\n\n"
            "Send me an IP address or ask me to investigate something.\n\n"
            "Examples:\n"
            "- 'Investigate 181.196.28.68'\n"
            "- 'Is 200.109.114.147 spoofing or legitimate?'\n"
            "- 'Tell me about pmg.produccion.gob.ec'\n\n"
            "I have access to dig, whois, host, and nslookup commands."
        )

    context.logger.info(f"User message: {user_message[:100]}")

    # Initialize tracing
    trace = InvestigationTrace(user_message=user_message)

    # Configure Claude with Bash tool access
    options = ClaudeAgentOptions(
        allowed_tools=["Bash"],
        disallowed_tools=["WebSearch", "WebFetch", "Grep"],
        max_turns=20,
        model="claude-sonnet-4-5",
        # hooks={"PreToolUse": [HookMatcher(matcher="Bash", hooks=[safety_hook])]},
    )

    try:
        # Just pass the user's message directly to Claude
        async with ClaudeSDKClient(options=options) as client:
            await client.query(user_message)

            # Collect Claude's response and trace all events
            result_text = ""
            async for message in client.receive_response():
                # Log and trace based on message type
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            result_text += block.text
                            trace.add_event(
                                "assistant_text", {"text": block.text[:200]}
                            )
                        elif isinstance(block, ToolUseBlock):
                            # Log tool usage
                            # Extract command - input might be dict or have different structure
                            command = ""
                            if isinstance(block.input, dict):
                                command = block.input.get("command", "")
                            elif hasattr(block.input, "command"):
                                command = block.input.command

                            tool_event = {
                                "tool": block.name,
                                "command": command,
                                "tool_use_id": block.id,
                                "raw_input": str(block.input)[
                                    :200
                                ],  # Keep raw for debugging
                            }
                            trace.add_event("tool_use", tool_event)

                            # Only log if we have a command
                            if command:
                                context.logger.info(f"🔧 Claude executing: {command}")
                            else:
                                context.logger.info(
                                    f"🔧 Claude using tool: {block.name} (input: {str(block.input)[:100]})"
                                )

                    # Track token usage from assistant messages
                    if hasattr(message, "usage") and message.usage:
                        trace.record_usage(message.usage)

                elif isinstance(message, UserMessage):
                    # Tool results come in UserMessage as ToolResultBlock
                    for content_block in message.content:
                        if isinstance(content_block, ToolResultBlock):
                            result_preview = str(content_block.content)[:200]
                            trace.add_event(
                                "tool_result",
                                {
                                    "tool_use_id": content_block.tool_use_id,
                                    "result_preview": result_preview,
                                    "is_error": getattr(
                                        content_block, "is_error", False
                                    ),
                                },
                            )

                elif isinstance(message, ResultMessage):
                    # Final result with cumulative cost
                    trace.finalize(message)

                    # Safely access usage (might be dict or object)
                    usage = message.usage
                    input_tokens = (
                        usage.get("input_tokens", 0)
                        if isinstance(usage, dict)
                        else getattr(usage, "input_tokens", 0)
                    )
                    output_tokens = (
                        usage.get("output_tokens", 0)
                        if isinstance(usage, dict)
                        else getattr(usage, "output_tokens", 0)
                    )

                    context.logger.info(
                        f"💰 Total cost: ${message.total_cost_usd:.6f} | "
                        f"Tokens: {input_tokens} in, {output_tokens} out"
                    )

            # Save trace to KV store for auditing
            await save_trace_to_kv(context, trace)

            context.logger.info(
                f"✅ Investigation completed in {trace.duration_seconds:.2f}s"
            )
            return response.text(result_text)

    except Exception as e:
        context.logger.error(f"Error during investigation: {e}", exc_info=True)
        return response.text(
            f"Sorry, I encountered an error while investigating:\n\n{str(e)}\n\n"
            "Please try again or contact support if the issue persists."
        )


async def safety_hook(input_data, tool_use_id, context):
    """
    Safety hook - only allow safe, read-only network investigation commands.
    """
    if input_data["tool_name"] != "Bash":
        return {}

    command = input_data["tool_input"].get("command", "")

    # Block dangerous patterns
    dangerous = [
        "rm",
        "sudo",
        "chmod",
        "chown",
        "dd",
        "mkfs",
        ">",
        ">>",
        "|",
        ";",
        "&&",
        "||",
        "curl",
        "wget",
        "..",
        "/etc",
        "/usr",
        "/var",
    ]

    for pattern in dangerous:
        if pattern in command:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Blocked dangerous pattern: {pattern}",
                }
            }

    # Only allow network investigation tools
    allowed = ["dig", "host", "whois", "nslookup", "ping", "traceroute"]

    if not any(cmd in command.lower() for cmd in allowed):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Only network investigation commands allowed",
            }
        }

    return {}  # Allow


class InvestigationTrace:
    """
    Tracks the complete execution trace of an IP investigation.
    Records all events, tool usage, token consumption, and costs.
    """

    def __init__(self, user_message: str):
        self.user_message = user_message
        self.start_time = datetime.now(timezone.utc)
        self.end_time = None
        self.events = []
        self.tool_uses = []
        self.token_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
        self.total_cost_usd = 0.0
        self.model = "claude-sonnet-4-5"

    def add_event(self, event_type: str, data: dict):
        """Add an event to the trace timeline"""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "data": data,
        }
        self.events.append(event)

        # Track tool uses separately for easy analysis
        if event_type == "tool_use":
            self.tool_uses.append(
                {
                    "command": data.get("command", ""),
                    "timestamp": event["timestamp"],
                    "tool_use_id": data.get("tool_use_id", ""),
                }
            )

    def record_usage(self, usage):
        """Record token usage from a message (handles dict or object)"""

        def get_value(obj, key, default=0):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        self.token_usage["input_tokens"] += get_value(usage, "input_tokens") or 0
        self.token_usage["output_tokens"] += get_value(usage, "output_tokens") or 0
        self.token_usage["cache_creation_input_tokens"] += (
            get_value(usage, "cache_creation_input_tokens") or 0
        )
        self.token_usage["cache_read_input_tokens"] += (
            get_value(usage, "cache_read_input_tokens") or 0
        )

    def finalize(self, result_message: ResultMessage):
        """Finalize trace with cumulative cost and usage (handles dict or object)"""
        self.end_time = datetime.now(timezone.utc)
        self.total_cost_usd = result_message.total_cost_usd

        # Use authoritative usage from result message
        if hasattr(result_message, "usage") and result_message.usage:
            usage = result_message.usage

            def get_value(obj, key, default=0):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            self.token_usage = {
                "input_tokens": get_value(usage, "input_tokens"),
                "output_tokens": get_value(usage, "output_tokens"),
                "cache_creation_input_tokens": get_value(
                    usage, "cache_creation_input_tokens"
                ),
                "cache_read_input_tokens": get_value(usage, "cache_read_input_tokens"),
            }

    @property
    def duration_seconds(self) -> float:
        """Calculate duration of investigation"""
        end = self.end_time or datetime.now(timezone.utc)
        return (end - self.start_time).total_seconds()

    def to_dict(self) -> dict:
        """Convert trace to dictionary for storage"""
        return {
            "user_message": self.user_message,
            "model": self.model,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "events": self.events,
            "tool_uses": self.tool_uses,
            "token_usage": self.token_usage,
            "total_cost_usd": self.total_cost_usd,
            "summary": {
                "total_events": len(self.events),
                "total_tool_uses": len(self.tool_uses),
                "commands_executed": [t["command"] for t in self.tool_uses],
            },
        }


async def save_trace_to_kv(context: AgentContext, trace: InvestigationTrace):
    """
    Save investigation trace to Agentuity KV store for auditing and analysis.

    Traces are stored with keys like: ip_investigation_20251204_143022
    """
    try:
        # Generate storage key with timestamp
        timestamp = trace.start_time.strftime("%Y%m%d_%H%M%S")
        storage_key = f"ip_investigation_{timestamp}"

        # Save to KV store
        await context.kv.set("ip-analyzer-traces", storage_key, trace.to_dict())

        context.logger.info(f"📊 Trace saved to KV store: {storage_key}")
    except Exception as e:
        context.logger.error(f"Failed to save trace to KV store: {e}")
        # Don't fail the request if trace saving fails
