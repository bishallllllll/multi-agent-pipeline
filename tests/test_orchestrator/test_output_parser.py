import os
import tempfile


from orchestrator.core.output_parser import OutputParser


class TestOutputParser:
    def test_parse_stream_empty(self):
        parser = OutputParser()
        result = parser.parse_stream("")
        assert result["text"] == ""
        assert result["code_blocks"] == []
        assert result["tokens"] == 0
        assert result["error"] is None

    def test_parse_stream_text_events(self):
        parser = OutputParser()
        stream = (
            '{"type": "text", "part": {"type": "text", "text": "Hello "}}\n'
            '{"type": "text", "part": {"type": "text", "text": "World"}}\n'
        )
        result = parser.parse_stream(stream)
        assert result["text"] == "Hello World"
        assert result["success"] is True

    def test_parse_stream_step_finish(self):
        parser = OutputParser()
        stream = (
            '{"type": "text", "part": {"type": "text", "text": "output"}}\n'
            '{"type": "step_finish", "part": {"tokens": {"total": 150}, "reason": "done"}}\n'
        )
        result = parser.parse_stream(stream)
        assert result["tokens"] == 150
        assert result["success"] is True

    def test_parse_stream_error(self):
        parser = OutputParser()
        stream = (
            '{"type": "text", "part": {"type": "text", "text": "partial"}}\n'
            '{"type": "step_finish", "part": {"tokens": {"total": 0}, "reason": "error", "error": "API error"}}\n'
        )
        result = parser.parse_stream(stream)
        assert result["error"] == "API error"
        assert result["success"] is False

    def test_parse_stream_event_error(self):
        parser = OutputParser()
        stream = '{"type": "error", "error": {"message": "Connection failed"}}\n'
        result = parser.parse_stream(stream)
        assert result["error"] == "Connection failed"
        assert result["success"] is False

    def test_parse_stream_bad_json_line(self):
        parser = OutputParser()
        stream = "not json\n" + '{"type": "text", "part": {"type": "text", "text": "good"}}\n'
        result = parser.parse_stream(stream)
        assert "good" in result["text"]

    def test_parse_stream_unknown_event_type(self):
        parser = OutputParser()
        stream = '{"type": "unknown_event", "data": {}}\n'
        result = parser.parse_stream(stream)
        assert result["text"] == ""
        assert result["success"] is False

    def test_extract_code_blocks(self):
        parser = OutputParser()
        blocks = parser._extract_code_blocks("```python\nprint('hello')\n```")
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"
        assert blocks[0]["extension"] == ".py"

    def test_extract_code_blocks_no_language(self):
        parser = OutputParser()
        blocks = parser._extract_code_blocks("```\nplain\n```")
        assert len(blocks) == 1
        assert blocks[0]["language"] == "text"
        assert blocks[0]["extension"] == ".text"

    def test_extract_code_blocks_unknown_language(self):
        parser = OutputParser()
        blocks = parser._extract_code_blocks("```foobar\ncode\n```")
        assert len(blocks) == 1
        assert blocks[0]["language"] == "foobar"
        assert blocks[0]["extension"] == ".foobar"

    def test_save_artifacts(self):
        parser = OutputParser()
        with tempfile.TemporaryDirectory() as tmpdir:
            blocks = [
                {"language": "python", "content": "print(1)", "extension": ".py"},
                {"language": "json", "content": '{"a": 1}', "extension": ".json"},
            ]
            saved = parser.save_artifacts(blocks, tmpdir, prefix="test_")
            assert len(saved) == 2
            assert os.path.exists(saved[0])
            assert os.path.exists(saved[1])
            with open(saved[0]) as f:
                assert f.read() == "print(1)"

    def test_save_artifacts_creates_dirs(self):
        parser = OutputParser()
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "nested", "dir")
            blocks = [{"language": "text", "content": "content", "extension": ".txt"}]
            saved = parser.save_artifacts(blocks, subdir)
            assert len(saved) == 1
            assert os.path.exists(saved[0])

    def test_extract_summary(self):
        parser = OutputParser()
        text = "This is the first paragraph.\n\nThis is the second paragraph."
        summary = parser.extract_summary(text)
        assert "first paragraph" in summary
        assert "second paragraph" not in summary

    def test_extract_summary_removes_code_blocks(self):
        parser = OutputParser()
        text = "```python\ncode here\n```\n\nThis is the result."
        summary = parser.extract_summary(text)
        assert "[code]" in summary

    def test_extract_summary_strips_markdown_headers(self):
        parser = OutputParser()
        text = "#  \n\nContent paragraph."
        summary = parser.extract_summary(text)
        assert "Content paragraph" in summary
        assert "Content paragraph" in summary

    def test_extract_summary_truncates(self):
        parser = OutputParser()
        text = "Short."
        summary = parser.extract_summary(text, max_length=3)
        assert len(summary) <= 6  # "..." appended

    def test_extract_summary_empty(self):
        parser = OutputParser()
        result = parser.extract_summary("")
        assert result == ""
