"""Tests for config utilities."""

import os
import tempfile

from ledgerloop.utils.config import load_config


class TestLoadConfig:
    def test_loads_simple_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("KEY=value\n")
            path = f.name
        try:
            config = load_config(path, apply=False)
            assert config == {"KEY": "value"}
        finally:
            os.unlink(path)

    def test_strips_inline_comment(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write('KEY=value # this is a comment\n')
            path = f.name
        try:
            config = load_config(path, apply=False)
            assert config == {"KEY": "value"}
        finally:
            os.unlink(path)

    def test_skips_comments(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("# comment line\nKEY=value\n")
            path = f.name
        try:
            config = load_config(path, apply=False)
            assert config == {"KEY": "value"}
        finally:
            os.unlink(path)

    def test_missing_file_returns_empty(self):
        config = load_config("/nonexistent/path.env", apply=False)
        assert config == {}

    def test_does_not_override_existing_env(self):
        os.environ["EXISTING_KEY"] = "existing_value"
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
                f.write("EXISTING_KEY=new_value\n")
                path = f.name
            config = load_config(path, apply=True)
            assert config == {"EXISTING_KEY": "new_value"}
            assert os.environ["EXISTING_KEY"] == "existing_value"
        finally:
            os.unlink(path)
            del os.environ["EXISTING_KEY"]

class TestShellStyleLines:
    def test_an_export_prefix_is_not_part_of_the_key(self, tmp_path):
        # The same file is often `source`d by a shell, which needs the export.
        path = tmp_path / ".env"
        path.write_text("export ANTHROPIC_API_KEY=sk-test\n", encoding="utf-8")
        assert load_config(path, apply=False) == {"ANTHROPIC_API_KEY": "sk-test"}

    def test_an_exported_key_reaches_the_environment(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text("export LEDGERLOOP_TEST_EXPORTED=yes\n", encoding="utf-8")
        try:
            load_config(path, apply=True)
            assert os.environ["LEDGERLOOP_TEST_EXPORTED"] == "yes"
        finally:
            os.environ.pop("LEDGERLOOP_TEST_EXPORTED", None)

    def test_a_key_that_merely_starts_with_export_is_left_alone(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text("EXPORT_FORMAT=csv\nexporter=sftp\n", encoding="utf-8")
        assert load_config(path, apply=False) == {"EXPORT_FORMAT": "csv", "exporter": "sftp"}

    def test_a_line_with_no_key_is_skipped(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text("=orphan\nKEY=value\n", encoding="utf-8")
        assert load_config(path, apply=False) == {"KEY": "value"}


class TestQuotedValues:
    def test_hash_inside_quotes_is_part_of_the_value(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text('DB_PASSWORD="hunter #2"\n', encoding="utf-8")
        assert load_config(path, apply=False) == {"DB_PASSWORD": "hunter #2"}

    def test_hash_inside_single_quotes_is_part_of_the_value(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text("WEBHOOK='https://example.test/hook #main'\n", encoding="utf-8")
        assert load_config(path, apply=False) == {"WEBHOOK": "https://example.test/hook #main"}

    def test_comment_after_the_closing_quote_is_dropped(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text('REGION="ap-south-1" # primary\n', encoding="utf-8")
        assert load_config(path, apply=False) == {"REGION": "ap-south-1"}

    def test_unclosed_quote_is_trimmed_as_before(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text('KEY="dangling\n', encoding="utf-8")
        assert load_config(path, apply=False) == {"KEY": "dangling"}

    def test_empty_quoted_value_is_empty(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text('KEY=""\n', encoding="utf-8")
        assert load_config(path, apply=False) == {"KEY": ""}
