import json
from orchestrator.core.output_parser import OutputParser


class TestOutputParser:
    def setup_method(self):
        self.parser = OutputParser()

    def test_parse_empty_stream(self):
        result = self.parser.parse_stream("")
        assert result["text"] == ""
        assert result["code_blocks"] == []
        assert result["tokens"] == 0

    def test_parse_text_event(self):
        stream = json.dumps({"type": "text", "part": {"type": "text", "text": "hello"}})
        result = self.parser.parse_stream(stream)
        assert "hello" in result["text"]

    def test_parse_step_finish_event(self):
        stream = json.dumps({"type": "step_finish", "part": {"tokens": {"total": 42}, "reason": "done"}})
        result = self.parser.parse_stream(stream)
        assert result["tokens"] == 42
        assert result["success"] is False

    def test_parse_error_event(self):
        stream = json.dumps({"type": "error", "error": {"message": "something broke"}})
        result = self.parser.parse_stream(stream)
        assert result["error"] == "something broke"

    def test_parse_multiple_events(self):
        events = [
            {"type": "text", "part": {"type": "text", "text": "Hello\n"}},
            {"type": "text", "part": {"type": "text", "text": "World"}},
            {"type": "step_finish", "part": {"tokens": {"total": 100}, "reason": "done"}},
        ]
        stream = "\n".join(json.dumps(e) for e in events)
        result = self.parser.parse_stream(stream)
        assert result["text"] == "Hello\nWorld"
        assert result["tokens"] == 100

    def test_parse_invalid_json_line(self):
        stream = "not json\n"
        result = self.parser.parse_stream(stream)
        assert result["text"] == ""
        assert result["error"] is None

    def test_extract_code_blocks_no_blocks(self):
        blocks = self.parser._extract_code_blocks("plain text")
        assert blocks == []

    def test_extract_code_blocks_with_lang(self):
        text = "```python\nprint('hello')\n```"
        blocks = self.parser._extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"
        assert blocks[0]["extension"] == ".py"

    def test_extract_code_blocks_unknown_lang(self):
        text = "```foo\nbar\n```"
        blocks = self.parser._extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "foo"
        assert blocks[0]["extension"] == ".foo"

    def test_save_artifacts(self, tmp_path):
        blocks = [
            {"language": "python", "content": "print('hello')", "extension": ".py"},
        ]
        saved = self.parser.save_artifacts(blocks, str(tmp_path), prefix="test_")
        assert len(saved) == 1
        assert saved[0].endswith(".py")
        with open(saved[0]) as f:
            assert f.read() == "print('hello')"

    def test_extract_summary_short_text(self):
        summary = self.parser.extract_summary("Short text", max_length=200)
        assert summary == "Short text"

    def test_extract_summary_long_text(self):
        text = "A" * 300
        summary = self.parser.extract_summary(text, max_length=100)
        assert len(summary) == 103

    def test_extract_summary_removes_code_blocks(self):
        text = "Here is the code:\n```python\nx = 1\n```\nDone."
        summary = self.parser.extract_summary(text)
        assert "[code]" in summary
