"""Tests for the footer that says why a Claude run stopped (#230, #172)."""

from src.bot.utils.formatting import format_permission_denials, format_stop_reason
from src.claude.sdk_integration import ClaudeResponse


def _response(**kwargs) -> ClaudeResponse:
    defaults = {
        "content": "Some output",
        "session_id": "s1",
        "cost": 0.01,
        "duration_ms": 100,
        "num_turns": 10,
    }
    defaults.update(kwargs)
    return ClaudeResponse(**defaults)


class TestFormatStopReason:
    """The footer appended to Claude's reply."""

    def test_no_footer_for_a_clean_run(self):
        assert format_stop_reason(_response(result_subtype="success")) is None

    def test_no_footer_when_the_cli_reported_no_subtype(self):
        """Older CLI versions omit subtype; that must not read as a failure."""
        assert format_stop_reason(_response()) is None

    def test_turn_limit(self):
        footer = format_stop_reason(
            _response(result_subtype="error_max_turns", terminal_reason="max_turns")
        )

        assert footer is not None
        assert "turn limit reached after 10 turns" in footer
        assert "Send a message to continue" in footer
        assert footer.startswith("\n\n")

    def test_turn_limit_without_a_terminal_reason(self):
        """subtype alone is enough; terminal_reason is extra detail."""
        footer = format_stop_reason(_response(result_subtype="error_max_turns"))

        assert footer is not None
        assert "turn limit reached" in footer

    def test_cost_budget(self):
        """CLAUDE_MAX_COST_PER_REQUEST is passed to the SDK as max_budget_usd."""
        footer = format_stop_reason(_response(result_subtype="error_max_budget_usd"))

        assert footer is not None
        assert "cost budget reached" in footer

    def test_error_during_execution_shows_the_cli_prose(self):
        footer = format_stop_reason(
            _response(
                result_subtype="error_during_execution",
                errors=["Tool ran out of memory"],
            )
        )

        assert footer is not None
        assert "the run hit an error" in footer
        assert "Tool ran out of memory" in footer

    def test_unknown_subtype_names_the_raw_value(self):
        footer = format_stop_reason(_response(result_subtype="error_brand_new"))

        assert footer is not None
        assert "error_brand_new" in footer

    def test_terminal_reason_wins_over_an_unknown_subtype(self):
        footer = format_stop_reason(
            _response(result_subtype="error_something", terminal_reason="api_error")
        )

        assert footer is not None
        assert "the API returned an error" in footer

    def test_no_turn_count_when_none_were_recorded(self):
        footer = format_stop_reason(
            _response(result_subtype="error_max_turns", num_turns=0)
        )

        assert footer is not None
        assert "after" not in footer

    def test_long_error_detail_is_clipped(self):
        footer = format_stop_reason(
            _response(result_subtype="error_during_execution", errors=["x" * 500])
        )

        assert footer is not None
        assert "…" in footer
        assert len(footer) < 400

    def test_denials_are_reported_even_on_a_successful_run(self):
        footer = format_stop_reason(
            _response(
                result_subtype="success",
                permission_denials=[
                    {"tool_name": "Write", "tool_input": {"file_path": "/etc/hosts"}}
                ],
            )
        )

        assert footer is not None
        assert "1 tool call was blocked: Write(/etc/hosts)" in footer
        assert "Stopped" not in footer

    def test_stop_line_and_denials_together(self):
        footer = format_stop_reason(
            _response(
                result_subtype="error_max_turns",
                permission_denials=[{"tool_name": "Bash", "tool_input": {}}],
            )
        )

        assert footer is not None
        assert "turn limit reached" in footer
        assert "1 tool call was blocked: Bash" in footer


class TestFormatPermissionDenials:
    """The blocked-calls line."""

    def test_none_when_nothing_was_denied(self):
        assert format_permission_denials([]) is None

    def test_plural_wording_and_argument_extraction(self):
        line = format_permission_denials(
            [
                {"tool_name": "Write", "tool_input": {"file_path": "/etc/hosts"}},
                {"tool_name": "Bash", "tool_input": {"command": "cd /"}},
            ]
        )

        assert line == "🚫 2 tool calls were blocked: Write(/etc/hosts), Bash(cd /)"

    def test_tool_without_a_recognised_argument(self):
        line = format_permission_denials([{"tool_name": "WebSearch", "tool_input": {}}])

        assert line == "🚫 1 tool call was blocked: WebSearch"

    def test_long_arguments_are_clipped(self):
        line = format_permission_denials(
            [{"tool_name": "Bash", "tool_input": {"command": "echo " + "a" * 200}}]
        )

        assert line is not None
        assert "…" in line
        assert len(line) < 100

    def test_whitespace_in_arguments_is_collapsed(self):
        line = format_permission_denials(
            [{"tool_name": "Bash", "tool_input": {"command": "ls\n  -la"}}]
        )

        assert line == "🚫 1 tool call was blocked: Bash(ls -la)"

    def test_long_lists_are_summarised(self):
        denials = [{"tool_name": f"Tool{i}", "tool_input": {}} for i in range(8)]

        line = format_permission_denials(denials)

        assert line is not None
        assert line.startswith("🚫 8 tool calls were blocked:")
        assert "and 3 more" in line
        assert "Tool5" not in line

    def test_non_dict_entries_are_ignored(self):
        """permission_denials is typed list[Any]; the CLI payload is opaque."""
        assert format_permission_denials(["not a dict", None]) is None

    def test_non_list_input_is_ignored(self):
        assert format_permission_denials(None) is None

    def test_missing_tool_name_falls_back(self):
        line = format_permission_denials([{"tool_input": {"file_path": "/x"}}])

        assert line == "🚫 1 tool call was blocked: unknown(/x)"
