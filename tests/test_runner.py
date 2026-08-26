from pipeline.runner import FULL_LOG_MAX_CHARS
from pipeline.runner import PipelineReport
from pipeline.runner import StepReport


def test_text_summary_truncates_long_full_log():
    report = PipelineReport(full_log="x" * 16000)
    summary = report.text_summary()
    assert "完整日志" in summary
    assert "已截断" in summary
    assert len(summary) <= FULL_LOG_MAX_CHARS + 100


def test_text_summary_short_full_log_not_truncated():
    report = PipelineReport(full_log="short log content")
    summary = report.text_summary()
    assert "完整日志" in summary
    assert "已截断" not in summary


def test_progress_summary_contains_arrow_line_for_done_step():
    step = StepReport(name="git更新代码", ok=True, log="a\nb", duration=1.0)
    report = PipelineReport(steps=[step])
    summary = report.progress_summary()
    assert "↳" in summary
    assert "git更新代码" in summary
    assert "b" in summary