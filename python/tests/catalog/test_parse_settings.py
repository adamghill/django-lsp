from dataclasses import asdict

import pytest
from django_lsp.generator.parse_settings import (
    DjangoSetting,
    clean_rst_markup,
    determine_category,
    extract_code_example,
    parse_settings_rst,
    slugify,
    strip_trailing_pointers,
)


@pytest.fixture
def mock_setting() -> DjangoSetting:
    return DjangoSetting(
        label="TEST_SETTING",
        description="A longer description of the test setting.",
        example="TEST_SETTING = 'example'",
        default="'default'",
        docs_url="https://example.com",
        nested_in=None,
        name="TEST_SETTING",
    )


def test_slugify():
    assert slugify("TEST_SETTING") == "test-setting"
    assert slugify("MY_COOL_SETTING") == "my-cool-setting"


def test_strip_trailing_pointers():
    text = "Some description.\n\nThe following options are available."
    assert strip_trailing_pointers(text) == "Some description."

    text = "Another one.\nSee below for more."
    assert strip_trailing_pointers(text) == "Another one."

    text = "Normal text."
    assert strip_trailing_pointers(text) == "Normal text."


def test_clean_rst_markup():
    text = "This is ``code`` and :ref:`ref`."
    assert clean_rst_markup(text) == "This is `code` and ref."

    text = ".. note::\n\n    This is a note."
    assert clean_rst_markup(text) == ""


def test_extract_code_example():
    text = """
Some text.

::

    CODE = 'example'
    MORE_CODE = 1

More text.
"""
    expected = "CODE = 'example'\nMORE_CODE = 1"
    assert extract_code_example(text) == expected


def test_determine_category():
    assert determine_category("AUTH_USER_MODEL", None) == "Auth"
    assert determine_category("CSRF_COOKIE_NAME", None) == "Security"
    assert determine_category("DATABASES", None) == "Databases"
    assert determine_category("UNKNOWN_SETTING", None) == "Core"
    assert determine_category("ENGINE", "DATABASES") == "Databases"


def test_parse_settings_rst():
    rst_content = """
.. setting:: TEST_SETTING

TEST_SETTING
------------

Default: ``'default'``

This is a test setting description.

::

    TEST_SETTING = 'value'
"""
    settings = parse_settings_rst(rst_content)
    assert len(settings) == 1
    s = settings[0]
    assert s.label == "TEST_SETTING"
    assert s.default == "'default'"
    # Description includes the code example in the current implementation
    expected_description = (
        "This is a test setting description.\n\n::\n\n    TEST_SETTING = 'value'"
    )
    assert s.description.strip() == expected_description.strip()
    assert s.example == "TEST_SETTING = 'value'"
    assert (
        s.docs_url
        == "https://docs.djangoproject.com/en/stable/ref/settings/#test-setting"
    )
    assert s.nested_in is None


def test_to_dict_serialization(mock_setting):
    # This logic matches what is inside run() in parse_settings.py
    def to_dict(s: DjangoSetting) -> dict:
        d = asdict(s)
        del d["nested_in"], d["rst_name"], d["parent_labels"]
        d["docsUrl"] = d.pop("docs_url")
        if d["children"] is None:
            del d["children"]
        else:
            d["children"] = [to_dict(c) for c in s.children]
        if not d["deprecated"]:
            del d["deprecated"]
        return d

    data = to_dict(mock_setting)

    assert "docsUrl" in data
    assert "docs_url" not in data
    assert "nested_in" not in data
    assert "rst_name" not in data
    assert data["docsUrl"] == "https://example.com"


def test_run_with_metadata(tmp_path):
    from django_lsp.generator.parse_settings import run

    rst_file = tmp_path / "settings.txt"
    rst_file.write_text(
        ".. setting:: DEBUG\n\nDEBUG\n-----\n\nDefault: ``False``\n", encoding="utf-8"
    )
    output_file = tmp_path / "settings.json"
    metadata = {"sha": "abc", "date": "2024-01-01", "url": "http://example.com"}

    run(rst_file, output_file, metadata=metadata)

    import json

    result = json.loads(output_file.read_text(encoding="utf-8"))
    assert result["sha"] == "abc"
    assert result["date"] == "2024-01-01"
    assert result["url"] == "http://example.com"
    assert len(result["data"]) == 1
    assert result["data"][0]["label"] == "DEBUG"


def test_run_with_extra_settings(tmp_path):
    from django_lsp.generator.parse_settings import run

    rst_file = tmp_path / "settings.txt"
    rst_file.write_text(
        ".. setting:: DEBUG\n\nDEBUG\n-----\n\nDefault: ``False``\n", encoding="utf-8"
    )
    output_file = tmp_path / "settings.json"

    # Create extra_settings.json in the same directory as output
    extra_file = tmp_path / "extra_settings.json"
    extra_file.write_text(
        '[{"label": "BASE_DIR", "name": "BASE_DIR", "category": "Project"}]',
        encoding="utf-8",
    )

    run(rst_file, output_file)

    import json

    result = json.loads(output_file.read_text(encoding="utf-8"))
    labels = [s["label"] for s in result["data"]]
    assert "BASE_DIR" in labels
    assert "DEBUG" in labels
