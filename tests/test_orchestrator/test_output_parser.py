from orchestrator.core.output_parser import OutputParser


class TestOutputParser:
    def setup_method(self):
        self.parser = OutputParser()

    def test_parse_stream_empty(self):
        result = self.parser.parse_stream("")
        assert result["text"] == ""
        assert result["code_blocks"] == []
        assert result["tokens"] == 0
        assert result["error"] is None

    def test_parse_stream_text_event(self):
        stream = '{"type": "text", "part": {"type": "text", "text": "hello"}}\n'
        result = self.parser.parse_stream(stream)
        assert result["text"] == "hello"
        assert result["success"] is True

    def test_parse_stream_step_finish(self):
        stream = (
            '{"type": "text", "part": {"type": "text", "text": "done"}}\n'
            '{"type": "step_finish", "part": {"tokens": {"total": 100}}}\n'
        )
        result = self.parser.parse_stream(stream)
        assert result["text"] == "done"
        assert result["tokens"] == 100

    def test_parse_stream_error_event(self):
        stream = '{"type": "error", "error": {"message": "something broke"}}\n'
        result = self.parser.parse_stream(stream)
        assert result["error"] == "something broke"

    def test_parse_stream_invalid_json(self):
        stream = "not json\n"
        result = self.parser.parse_stream(stream)
        assert result["text"] == ""

    def test_extract_code_blocks(self):
        text = "```python\nprint('hi')\n```"
        blocks = self.parser._extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"
        assert blocks[0]["extension"] == ".py"

    def test_extract_code_blocks_unknown_lang(self):
        text = "```foobar\ncode here\n```"
        blocks = self.parser._extract_code_blocks(text)
        assert blocks[0]["extension"] == ".foobar"

    def test_extract_code_blocks_multiple(self):
        text = "```py\na\n```\n```js\nb\n```"
        blocks = self.parser._extract_code_blocks(text)
        assert len(blocks) == 2

    def test_extract_code_blocks_none(self):
        assert self.parser._extract_code_blocks("no fences") == []

    def test_save_artifacts(self, tmp_path):
        blocks = [{"language": "python", "content": "print('hi')", "extension": ".py"}]
        saved = self.parser.save_artifacts(blocks, str(tmp_path), prefix="test_")
        assert len(saved) == 1
        assert saved[0].endswith(".py")
        assert (tmp_path / "test_.py").read_text() == "print('hi')"

    def test_save_artifacts_avoids_overwrite(self, tmp_path):
        (tmp_path / "test_.py").write_text("old")
        blocks = [{"language": "python", "content": "new", "extension": ".py"}]
        saved = self.parser.save_artifacts(blocks, str(tmp_path), prefix="test_")
        assert len(saved) == 1
        assert "0" in saved[0]

    def test_extract_summary_removes_code(self):
        summary = self.parser.extract_summary("Hello\n```python\nx=1\n```\nWorld", max_length=200)
        assert "[code]" in summary
        assert "x=1" not in summary

    def test_extract_summary_first_paragraph(self):
        summary = self.parser.extract_summary("First paragraph.\n\nSecond paragraph.", max_length=200)
        assert "First paragraph." in summary
        assert "Second paragraph." not in summary

    def test_extract_summary_truncates(self):
        text = "A" * 300
        summary = self.parser.extract_summary(text, max_length=100)
        assert len(summary) <= 103

    def test_extract_summary_removes_headers(self):
        summary = self.parser.extract_summary("# Title\n\nContent here", max_length=200)
        assert "# Title" not in summary
        assert "Title" in summary
