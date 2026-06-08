"""Unit 3 tests: WriterAgent and JudgeAgent.

All offline — FakeLLMProvider only, no DB, no network.
"""
import json

import pytest

from app.agents import JudgeAgent, JudgementResult, WriterAgent
from app.agents.judge import PROMPT_VERSION
from app.providers import FakeLLMProvider


BRIEF = {"title": "The Brave Little Snail", "age_range": "4-6", "theme": "courage"}
CRITERIA = {"age_range": "4-6", "genre": "adventure"}

_GOOD_JUDGEMENT = {
    "emotional_authenticity": 8.0,
    "representation_quality": 7.5,
    "pacing": 8.5,
    "age_fit": 9.0,
    "uniqueness": 7.0,
    "weighted_total": 8.0,
    "passed": True,
    "critique": {
        "emotional_authenticity": "Warm and relatable.",
        "representation_quality": "Characters feel authentic.",
        "pacing": "Moves well.",
        "age_fit": "Perfect for ages 4-6.",
        "uniqueness": "Fresh angle on courage.",
    },
}

_FAILING_JUDGEMENT = {**_GOOD_JUDGEMENT, "weighted_total": 6.0, "passed": False}


# ---------------------------------------------------------------------------
# WriterAgent
# ---------------------------------------------------------------------------

class TestWriterAgent:
    def test_returns_string(self):
        llm = FakeLLMProvider(responses=["Once upon a time..."])
        agent = WriterAgent(llm)
        result = agent.write(BRIEF, "three-act")
        assert result == "Once upon a time..."

    def test_calls_llm_once(self):
        llm = FakeLLMProvider(responses=["story"])
        WriterAgent(llm).write(BRIEF, "three-act")
        assert len(llm.calls) == 1

    def test_brief_appears_in_prompt(self):
        llm = FakeLLMProvider(responses=["story"])
        WriterAgent(llm).write(BRIEF, "three-act")
        user_content = llm.calls[0]["messages"][0]["content"]
        assert "Brave Little Snail" in user_content

    def test_method_guidance_appears_in_prompt(self):
        llm = FakeLLMProvider(responses=["story"])
        WriterAgent(llm).write(BRIEF, "sensory-first")
        user_content = llm.calls[0]["messages"][0]["content"]
        assert "sensory" in user_content.lower()

    def test_different_methods_produce_different_prompts(self):
        def prompt_for(method: str) -> str:
            llm = FakeLLMProvider(responses=["story"])
            WriterAgent(llm).write(BRIEF, method)
            return llm.calls[0]["messages"][0]["content"]

        prompts = {m: prompt_for(m) for m in ("three-act", "sensory-first", "problem-solution", "hero's-journey")}
        assert len(set(prompts.values())) == 4

    def test_prior_critique_appears_in_rewrite_prompt(self):
        llm = FakeLLMProvider(responses=["revised story"])
        critique = "DRAFT:\nOld text.\n\nCRITIQUE:\nNeeds more emotion."
        WriterAgent(llm).write(BRIEF, "three-act", prior_critique=critique)
        user_content = llm.calls[0]["messages"][0]["content"]
        assert "Needs more emotion" in user_content

    def test_rewrite_uses_revision_system_prompt(self):
        llm = FakeLLMProvider(responses=["revised"])
        WriterAgent(llm).write(BRIEF, "three-act", prior_critique="some critique")
        assert "revis" in llm.calls[0]["system"].lower()

    def test_fresh_write_does_not_use_revision_system_prompt(self):
        llm = FakeLLMProvider(responses=["story"])
        WriterAgent(llm).write(BRIEF, "three-act")
        assert "revis" not in llm.calls[0]["system"].lower()

    def test_unknown_method_raises(self):
        llm = FakeLLMProvider(responses=["story"])
        with pytest.raises(ValueError, match="Unknown writing method"):
            WriterAgent(llm).write(BRIEF, "interpretive-dance")

    def test_all_four_methods_accepted(self):
        for method in ("three-act", "sensory-first", "problem-solution", "hero's-journey"):
            llm = FakeLLMProvider(responses=["story"])
            result = WriterAgent(llm).write(BRIEF, method)
            assert isinstance(result, str)


# ---------------------------------------------------------------------------
# JudgeAgent
# ---------------------------------------------------------------------------

class TestJudgeAgent:
    def _good_llm(self, n: int = 1) -> FakeLLMProvider:
        return FakeLLMProvider(responses=[json.dumps(_GOOD_JUDGEMENT)] * n)

    def test_returns_list_of_judgement_results(self):
        agent = JudgeAgent(self._good_llm(2))
        results = agent.judge(["story one", "story two"], CRITERIA)
        assert len(results) == 2
        assert all(isinstance(r, JudgementResult) for r in results)

    def test_scores_are_correct(self):
        agent = JudgeAgent(self._good_llm())
        result = agent.judge(["story"], CRITERIA)[0]
        assert result.emotional_authenticity == 8.0
        assert result.weighted_total == 8.0

    def test_passed_computed_from_threshold_not_llm(self):
        # LLM says passed=True but weighted_total=6.0 < threshold=7.5
        llm = FakeLLMProvider(responses=[json.dumps(_FAILING_JUDGEMENT)])
        agent = JudgeAgent(llm, threshold=7.5)
        result = agent.judge(["story"], CRITERIA)[0]
        assert result.passed is False

    def test_passes_when_above_threshold(self):
        llm = FakeLLMProvider(responses=[json.dumps(_GOOD_JUDGEMENT)])
        agent = JudgeAgent(llm, threshold=7.5)
        result = agent.judge(["story"], CRITERIA)[0]
        assert result.passed is True

    def test_custom_threshold(self):
        llm = FakeLLMProvider(responses=[json.dumps(_GOOD_JUDGEMENT)])
        agent = JudgeAgent(llm, threshold=9.0)  # 8.0 < 9.0 → fails
        result = agent.judge(["story"], CRITERIA)[0]
        assert result.passed is False

    def test_critique_dict_preserved(self):
        agent = JudgeAgent(self._good_llm())
        result = agent.judge(["story"], CRITERIA)[0]
        assert result.critique["pacing"] == "Moves well."

    def test_story_appears_in_prompt(self):
        llm = self._good_llm()
        JudgeAgent(llm).judge(["A tale of a snail."], CRITERIA)
        user_content = llm.calls[0]["messages"][0]["content"]
        assert "A tale of a snail." in user_content

    def test_json_schema_passed_to_llm(self):
        llm = self._good_llm()
        JudgeAgent(llm).judge(["story"], CRITERIA)
        assert llm.calls[0]["json_schema"] is not None

    def test_prompt_version_is_accessible(self):
        assert JudgeAgent.PROMPT_VERSION == PROMPT_VERSION
        assert isinstance(PROMPT_VERSION, str)
        assert len(PROMPT_VERSION) > 0

    def test_one_llm_call_per_story(self):
        llm = self._good_llm(3)
        JudgeAgent(llm).judge(["a", "b", "c"], CRITERIA)
        assert len(llm.calls) == 3

    def test_retries_on_invalid_json(self):
        bad = "not json at all"
        good = json.dumps(_GOOD_JUDGEMENT)
        llm = FakeLLMProvider(responses=[bad, good])
        result = JudgeAgent(llm).judge(["story"], CRITERIA)[0]
        assert result.weighted_total == 8.0
        assert len(llm.calls) == 2  # one retry

    def test_retries_on_missing_field(self):
        incomplete = json.dumps({"emotional_authenticity": 7.0})
        good = json.dumps(_GOOD_JUDGEMENT)
        llm = FakeLLMProvider(responses=[incomplete, good])
        result = JudgeAgent(llm).judge(["story"], CRITERIA)[0]
        assert result.emotional_authenticity == 8.0

    def test_raises_after_three_failures(self):
        llm = FakeLLMProvider(responses=["bad", "bad", "bad"])
        with pytest.raises(RuntimeError, match="3 attempts"):
            JudgeAgent(llm).judge(["story"], CRITERIA)

    def test_error_response_fed_back_to_llm(self):
        bad = "oops"
        good = json.dumps(_GOOD_JUDGEMENT)
        llm = FakeLLMProvider(responses=[bad, good])
        JudgeAgent(llm).judge(["story"], CRITERIA)
        # Second call should include the bad response + correction request in messages
        second_call_messages = llm.calls[1]["messages"]
        assert any(bad in msg.get("content", "") for msg in second_call_messages)

    def test_score_out_of_range_triggers_retry(self):
        out_of_range = json.dumps({**_GOOD_JUDGEMENT, "emotional_authenticity": 11.0})
        good = json.dumps(_GOOD_JUDGEMENT)
        llm = FakeLLMProvider(responses=[out_of_range, good])
        result = JudgeAgent(llm).judge(["story"], CRITERIA)[0]
        assert result.emotional_authenticity == 8.0

    def test_empty_story_list_returns_empty(self):
        agent = JudgeAgent(FakeLLMProvider())
        assert agent.judge([], CRITERIA) == []
