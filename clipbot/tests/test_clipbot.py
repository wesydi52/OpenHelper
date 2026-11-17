from clipbot.detector import SpikeDetector
from clipbot.subtitles import to_srt, _ts


def test_no_spike_on_steady_chat():
    d = SpikeDetector()
    assert not any(d.push(c) for c in [20, 22, 19, 21, 23, 20, 22, 21, 20, 24])


def test_spike_detected_then_cooldown():
    d = SpikeDetector(cooldown_windows=3)
    for c in [20, 22, 19, 21, 23, 20, 22]:
        d.push(c)
    assert d.push(120)
    assert not d.push(130)  # кулдаун


def test_needs_history_and_min_msgs():
    d = SpikeDetector()
    assert not d.push(500)  # нет истории
    d2 = SpikeDetector(min_msgs=15)
    for c in [1, 2, 1, 2, 1, 2]:
        d2.push(c)
    assert not d2.push(10)  # ниже абсолютного минимума


def test_srt_format():
    assert _ts(3661.5) == "01:01:01,500"
    s = to_srt([(0, 1.5, " привет ")])
    assert s.startswith("1\n00:00:00,000 --> 00:00:01,500\nпривет")
