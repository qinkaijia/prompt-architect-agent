import pytest

from prompt_architect.analyzers import ComplexityScorer, RequirementAnalyzer
from prompt_architect.schemas import PromptStrategy


@pytest.mark.parametrize(
    ("score", "strategy"),
    [
        (0, PromptStrategy.COMPACT),
        (4, PromptStrategy.COMPACT),
        (5, PromptStrategy.STRUCTURED),
        (8, PromptStrategy.STRUCTURED),
        (9, PromptStrategy.STAGED),
        (13, PromptStrategy.STAGED),
        (14, PromptStrategy.PROJECT),
        (18, PromptStrategy.PROJECT),
    ],
)
def test_strategy_boundaries(score: int, strategy: PromptStrategy) -> None:
    assert ComplexityScorer.strategy_for_score(score) == strategy


def test_assessment_has_six_explained_dimensions() -> None:
    task = RequirementAnalyzer().analyze("让 Codex 修改一个 Python 函数，为函数增加输入参数检查。")
    assessment = ComplexityScorer().score(task)
    assert len(assessment.dimensions) == 6
    assert assessment.total_score == sum(item.score for item in assessment.dimensions.values())
    assert all(item.reason for item in assessment.dimensions.values())
