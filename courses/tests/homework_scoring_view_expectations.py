from dataclasses import dataclass


@dataclass(frozen=True)
class ScoredOptionExpectation:
    index: int
    value: str
    is_selected: bool
    is_correct: bool
    selected_class: str


def scored_option(expectation):
    option = {
        "value": expectation.value,
        "is_selected": expectation.is_selected,
        "index": expectation.index,
    }
    option["is_correct"] = expectation.is_correct
    option["correctly_selected_class"] = expectation.selected_class
    return option


def scored_options(expectations):
    options = []
    for expectation in expectations:
        option = scored_option(expectation)
        options.append(option)
    return options


FIRST_PARIS_OPTION = ScoredOptionExpectation(
    index=1,
    value="Paris",
    is_selected=False,
    is_correct=True,
    selected_class="option-answer-correct",
)
FIRST_LONDON_OPTION = ScoredOptionExpectation(
    index=2,
    value="London",
    is_selected=False,
    is_correct=False,
    selected_class="option-answer-none",
)
FIRST_BERLIN_OPTION = ScoredOptionExpectation(
    index=3,
    value="Berlin",
    is_selected=True,
    is_correct=False,
    selected_class="option-answer-incorrect",
)
FIRST_QUESTION_EXPECTATIONS = (
    FIRST_PARIS_OPTION,
    FIRST_LONDON_OPTION,
    FIRST_BERLIN_OPTION,
)

THIRD_TWO_OPTION = ScoredOptionExpectation(
    index=1,
    value="2",
    is_selected=True,
    is_correct=True,
    selected_class="option-answer-correct",
)
THIRD_THREE_OPTION = ScoredOptionExpectation(
    index=2,
    value="3",
    is_selected=True,
    is_correct=True,
    selected_class="option-answer-correct",
)
THIRD_FOUR_OPTION = ScoredOptionExpectation(
    index=3,
    value="4",
    is_selected=True,
    is_correct=False,
    selected_class="option-answer-incorrect",
)
THIRD_FIVE_OPTION = ScoredOptionExpectation(
    index=4,
    value="5",
    is_selected=False,
    is_correct=True,
    selected_class="option-answer-correct",
)
THIRD_QUESTION_EXPECTATIONS = (
    THIRD_TWO_OPTION,
    THIRD_THREE_OPTION,
    THIRD_FOUR_OPTION,
    THIRD_FIVE_OPTION,
)

FOURTH_FIVE_OPTION = ScoredOptionExpectation(
    index=1,
    value="5",
    is_selected=True,
    is_correct=False,
    selected_class="option-answer-incorrect",
)
FOURTH_SIX_OPTION = ScoredOptionExpectation(
    index=2,
    value="6",
    is_selected=False,
    is_correct=False,
    selected_class="option-answer-none",
)
FOURTH_SEVEN_OPTION = ScoredOptionExpectation(
    index=3,
    value="7",
    is_selected=False,
    is_correct=True,
    selected_class="option-answer-correct",
)
FOURTH_QUESTION_EXPECTATIONS = (
    FOURTH_FIVE_OPTION,
    FOURTH_SIX_OPTION,
    FOURTH_SEVEN_OPTION,
)

SIXTH_BLUE_OPTION = ScoredOptionExpectation(
    index=1,
    value="Blue",
    is_selected=True,
    is_correct=True,
    selected_class="option-answer-correct",
)
SIXTH_WHITE_OPTION = ScoredOptionExpectation(
    index=2,
    value="White",
    is_selected=True,
    is_correct=True,
    selected_class="option-answer-correct",
)
SIXTH_RED_OPTION = ScoredOptionExpectation(
    index=3,
    value="Red",
    is_selected=True,
    is_correct=True,
    selected_class="option-answer-correct",
)
SIXTH_GREEN_OPTION = ScoredOptionExpectation(
    index=4,
    value="Green",
    is_selected=False,
    is_correct=False,
    selected_class="option-answer-none",
)
SIXTH_QUESTION_EXPECTATIONS = (
    SIXTH_BLUE_OPTION,
    SIXTH_WHITE_OPTION,
    SIXTH_RED_OPTION,
    SIXTH_GREEN_OPTION,
)
