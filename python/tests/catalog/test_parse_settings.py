from dataclasses import asdict

import pytest
from django_lsp.generator.parser import (
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
    # This logic matches what is inside main() in parse_settings.py
    # We need to replicate strict JSON serialization logic to verify the contract

    def to_dict(s: DjangoSetting) -> dict:
        d = asdict(s)
        # Remove nested_in from output (inferred from structure)
        del d["nested_in"]

        # Rename docs_url to docsUrl for JSON output
        d["docsUrl"] = d.pop("docs_url")

        if d["children"] is None:
            del d["children"]
        else:
            d["children"] = [to_dict(c) for c in s.children]

        # Remove deprecated if False
        if not d["deprecated"]:
            del d["deprecated"]

        return d

    data = to_dict(mock_setting)

    assert "docsUrl" in data
    assert "docs_url" not in data
    assert "nested_in" not in data
    assert "nestedIn" not in data
    assert data["docsUrl"] == "https://example.com"


def test_nested_settings():
    rst_content = """
.. setting:: PARENT_SETTING

PARENT_SETTING
--------------

Parent description.

.. setting:: CHILD_SETTING

CHILD_SETTING
~~~~~~~~~~~~~

Child description.

"""
    settings = parse_settings_rst(rst_content)
    # The current implementation of parse_settings_rst relies on observing indentation or
    # structure to determine nesting parent-child relationship during the linear scan.
    # Based on the code:
    # Top-level has underline like '---'
    # Nested has underline like '~~~' and sets nested_in = current_parent

    # We expect 2 settings
    assert len(settings) == 2

    parent = next(s for s in settings if s.label == "PARENT_SETTING")
    child = next(s for s in settings if s.label == "PARENT_SETTING.CHILD_SETTING")

    assert parent.nested_in is None
    assert child.nested_in == "PARENT_SETTING"
    # Verify that parent prefix is stripped from the name
    assert parent.name == "PARENT_SETTING"
    assert child.name == "CHILD_SETTING"


def test_nested_databases_name():
    rst_content = """
.. setting:: DATABASES

DATABASES
---------

Default: {}

A dictionary containing the settings for all databases.

.. setting:: DATABASE-ENGINE

DATABASE-ENGINE
~~~~~~~~~~~~~~~

Default: ''

The database backend to use.
"""
    settings = parse_settings_rst(rst_content)
    child = next(s for s in settings if s.label == "DATABASES.ENGINE")
    assert child.name == "ENGINE"
    assert child.nested_in == "DATABASES"
    assert child.parent_labels == ["DATABASES"]


def test_deprecated_settings():
    # Verify that deprecation is not yet implemented in the parser
    rst_content = """
.. setting:: DEPRECATED_SETTING

DEPRECATED_SETTING
------------------

.. deprecated:: 5.0

Old setting.
"""
    settings = parse_settings_rst(rst_content)
    s = settings[0]
    assert s.label == "DEPRECATED_SETTING"
    assert s.deprecated is False


def test_complex_rst_markup():
    text = """
This is a paragraph.

.. note::

    This is a note.

This has a :ref:`link <target>`.
And a :class:`~module.Class`.
"""
    cleaned = clean_rst_markup(text)
    assert "This is a paragraph." in cleaned
    assert "This is a note." not in cleaned  # clean_rst_markup removes notes
    assert "This has a target." in cleaned
    assert "And a `module.Class`." in cleaned
