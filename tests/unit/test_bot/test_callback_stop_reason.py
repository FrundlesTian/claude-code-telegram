"""The classic-mode callbacks build HTML by hand, so they carry the footer too."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.bot.handlers.callback import (
    _stop_reason_html,
    handle_quick_action_callback,
)
from src.claude.sdk_integration import ClaudeResponse


def _response(**kwargs) -> ClaudeResponse:
    defaults = {
        "content": "Ran the checks.",
        "session_id": "s1",
        "cost": 0.01,
        "duration_ms": 100,
        "num_turns": 10,
    }
    defaults.update(kwargs)
    return ClaudeResponse(**defaults)


class TestStopReasonHtml:
    """format_stop_reason output converted for a hand-built HTML message."""

    def test_empty_for_a_clean_run(self):
        assert _stop_reason_html(_response(result_subtype="success")) == ""

    def test_turn_limit_renders_as_html(self):
        html = _stop_reason_html(_response(result_subtype="error_max_turns"))

        assert "turn limit reached after 10 turns" in html
        assert "<" not in html.replace("<code>", "").replace("</code>", "")

    def test_blocked_call_is_escaped_and_monospaced(self):
        html = _stop_reason_html(
            _response(
                result_subtype="success",
                permission_denials=[
                    {"tool_name": "Bash", "tool_input": {"command": "cd / && ls"}}
                ],
            )
        )

        assert "<code>cd / &amp;&amp; ls</code>" in html


async def _run_quick_action(claude_response, tmp_path):
    """Drive handle_quick_action_callback and return the text it replied with."""
    action = MagicMock()
    action.icon = "🔍"
    action.name = "Run tests"
    action.prompt = "run the tests"

    quick_actions = MagicMock()
    quick_actions.get_action = MagicMock(return_value=action)

    claude_integration = AsyncMock()
    claude_integration.run_command = AsyncMock(return_value=claude_response)

    settings = MagicMock()
    settings.approved_directory = tmp_path

    query = MagicMock()
    query.from_user.id = 123
    query.edit_message_text = AsyncMock()
    query.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {"current_directory": tmp_path}
    context.bot_data = {
        "quick_actions": quick_actions,
        "claude_integration": claude_integration,
        "settings": settings,
    }

    await handle_quick_action_callback(query, "test", context)

    assert query.message.reply_text.call_args is not None, "no reply was sent"
    return query.message.reply_text.call_args.args[0]


class TestQuickActionHeading:
    """The heading said "Complete" whatever the run did — #172 in a header."""

    async def test_clean_run_still_says_complete(self, tmp_path):
        text = await _run_quick_action(
            _response(result_subtype="success"), Path(tmp_path)
        )

        assert "Complete" in text
        assert "Stopped" not in text

    async def test_truncated_run_says_stopped_and_explains(self, tmp_path):
        text = await _run_quick_action(
            _response(result_subtype="error_max_turns", terminal_reason="max_turns"),
            Path(tmp_path),
        )

        assert "Complete" not in text
        assert "Stopped" in text
        assert "turn limit reached after 10 turns" in text
