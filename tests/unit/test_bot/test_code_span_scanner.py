r"""The inline-code pass runs on the event loop, so it has to stay linear.

Pairing equal-length backtick runs with a regex needs a backreference inside a
lazy middle -- ``(`+)([^\n]*?)\1`` -- which re-scans the rest of the line for
every opener that never finds a partner. On a reply whose backtick runs are
all of different lengths that is superlinear: the regex this replaced took
2.5 seconds on 256KB, blocking every other user's message for that long.
"""

import re
import time

from src.bot.utils.html_format import _extract_code_spans, markdown_to_telegram_html

# The pattern this scanner replaced, kept so the two can be compared directly.
BACKREF_PATTERN = re.compile(r"(?<!`)(`+)(?!`)([^\n]*?)(?<!`)\1(?!`)")


def _render(code: str) -> str:
    return f"[{code}]"


def _distinct_runs(size: int) -> str:
    """Backtick runs of every length, so no opener ever finds its closer."""
    parts, length = [], 1
    while sum(len(p) for p in parts) < size:
        parts.append("`" * length + "a")
        length += 1
    return "".join(parts)


class TestMatchesTheRegexItReplaced:
    """Same output, or the linearity fix would be a behaviour change."""

    CASES = [
        "Run `ls -la` then `cd /tmp`.",
        "Use ``a`b`` for a literal backtick.",
        "Blocked: Bash(`` `whoami` ``)",
        "unclosed ` backtick and `another` one",
        "multi\nline ` spanning ` attempt",
        "`  spaced  `",
        "` `",
        "``  ``",
        "``",
        "```",
        "a`b``c```d",
        "`x`\n`y`",
        "",
    ]

    @staticmethod
    def _via_regex(text: str) -> str:
        def replace(m: "re.Match[str]") -> str:
            code = m.group(2)
            if (
                len(code) >= 2
                and code[0] == " "
                and code[-1] == " "
                and code.strip(" ")
            ):
                code = code[1:-1]
            return _render(code)

        return BACKREF_PATTERN.sub(replace, text)

    def test_every_case_renders_identically(self):
        for case in self.CASES:
            assert _extract_code_spans(case, _render) == self._via_regex(
                case
            ), f"diverged on {case!r}"


class TestSpanSemantics:
    def test_a_run_closes_only_on_the_same_length(self):
        assert _extract_code_spans("``a`b``", _render) == "[a`b]"

    def test_an_unpaired_run_is_left_alone(self):
        assert _extract_code_spans("``a`b", _render) == "``a`b"

    def test_a_span_does_not_cross_a_newline(self):
        assert _extract_code_spans("`a\nb`", _render) == "`a\nb`"

    def test_one_space_is_stripped_from_each_end(self):
        assert _extract_code_spans("`` `x` ``", _render) == "[`x`]"

    def test_a_span_of_only_spaces_keeps_them(self):
        assert _extract_code_spans("`  `", _render) == "[  ]"

    def test_spans_after_an_unpaired_run_are_still_found(self):
        assert _extract_code_spans("``` then `a`", _render) == "``` then [a]"


class TestStaysLinear:
    """A ceiling with three orders of magnitude of headroom.

    The scanner does this in under a millisecond; the regex it replaced took
    ~2.5s. The bound is loose enough that only a return to superlinear
    behaviour can trip it, however slow the runner.
    """

    BUDGET_SECONDS = 1.0

    def test_pathological_input_converts_promptly(self):
        text = _distinct_runs(256_000)

        started = time.perf_counter()
        markdown_to_telegram_html(text)
        elapsed = time.perf_counter() - started

        assert elapsed < self.BUDGET_SECONDS, f"took {elapsed:.2f}s"

    def test_the_pathological_input_really_has_nothing_to_match(self):
        """Otherwise the budget above would be measuring an early exit."""
        text = _distinct_runs(64_000)

        assert _extract_code_spans(text, _render) == text
