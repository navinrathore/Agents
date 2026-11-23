from pathlib import Path
import sys
import pytest

AGENTS_ROOT = str(Path(__file__).resolve().parent.parent)
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)

from core.utils import RepetitionDetector


def test_consecutive_repetition_default():
    detector = RepetitionDetector(threshold=3)
    error = "OperationalError: connection to database failed"

    assert detector.check(error) is False
    assert detector.check(error) is False
    assert detector.check(error) is True  # 3rd consecutive


def test_non_consecutive_ping_pong_detection():
    detector = RepetitionDetector(threshold=3, window_size=10)
    error_a = "SyntaxError: unexpected EOF"
    error_b = "IndexError: list index out of range"

    # Ping-pong sequence: A -> B -> A -> B -> A
    assert detector.check(error_a) is False  # A count: 1
    assert detector.check(error_b) is False  # B count: 1
    assert detector.check(error_a) is False  # A count: 2
    assert detector.check(error_b) is False  # B count: 2
    assert detector.check(error_a) is True   # A count: 3 -> Caught non-consecutive loop!


def test_sliding_window_eviction():
    # Window size 4, threshold 3
    detector = RepetitionDetector(threshold=3, window_size=4)

    assert detector.check("err_1") is False  # [err_1]
    assert detector.check("err_1") is False  # [err_1, err_1]
    assert detector.check("err_2") is False  # [err_1, err_1, err_2]
    assert detector.check("err_3") is False  # [err_1, err_1, err_2, err_3]
    assert detector.check("err_4") is False  # [err_1, err_2, err_3, err_4] (one err_1 evicted)
    assert detector.check("err_5") is False  # [err_2, err_3, err_4, err_5] (both err_1 evicted)

    # err_1 now only has count 1 if added again
    assert detector.check("err_1") is False
    assert detector.get_count("err_1") == 1


def test_consecutive_only_mode():
    detector = RepetitionDetector(threshold=3, consecutive_only=True)

    # Alternating sequence should NOT trigger in consecutive_only mode
    assert detector.check("err_A") is False
    assert detector.check("err_B") is False
    assert detector.check("err_A") is False
    assert detector.check("err_B") is False
    assert detector.check("err_A") is False

    # Back-to-back sequence SHOULD trigger
    assert detector.check("err_C") is False
    assert detector.check("err_C") is False
    assert detector.check("err_C") is True


def test_empty_and_reset():
    detector = RepetitionDetector(threshold=3)

    assert detector.check("") is False
    assert detector.check("   ") is False
    assert detector.check(None) is False

    detector.check("err_X")
    detector.check("err_X")
    assert detector.get_count("err_X") == 2

    detector.reset()
    assert detector.get_count("err_X") == 0
    assert detector.check("err_X") is False
