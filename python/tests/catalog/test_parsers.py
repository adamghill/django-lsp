import json

from django_lsp.generator import (
    parse_fields,
    parse_functions,
    parse_lookups,
    parse_meta,
)


def test_parse_lookups(tmp_path):
    rst_file = tmp_path / "querysets.txt"
    rst_file.write_text(
        """
.. fieldlookup:: exact

exact
-----

Example::

    Entry.objects.get(id__exact=14)
""",
        encoding="utf-8",
    )
    output_file = tmp_path / "lookups.json"
    metadata = {"sha": "123", "date": "now", "url": "local"}

    parse_lookups.run(rst_file, output_file, metadata=metadata)

    result = json.loads(output_file.read_text(encoding="utf-8"))
    assert result["sha"] == "123"
    assert len(result["data"]) == 1
    assert result["data"][0]["name"] == "exact"


def test_parse_fields(tmp_path):
    rst_file = tmp_path / "fields.txt"
    rst_file.write_text(
        """
Field options
=============

.. attribute:: Field.null

null
~~~~

Example::

    null=True

Field types
===========

.. class:: CharField(max_length=None, **options)

CharField
---------

Example::

    name = models.CharField(max_length=100)

.. attribute:: CharField.max_length

max_length
~~~~~~~~~~

The description.
""",
        encoding="utf-8",
    )
    output_file = tmp_path / "fields.json"
    metadata = {"sha": "123", "date": "now", "url": "local"}

    parse_fields.run(rst_file, output_file, metadata=metadata)

    result = json.loads(output_file.read_text(encoding="utf-8"))
    assert result["data"]["fields"][0]["name"] == "CharField"
    assert result["data"]["fields"][0]["arguments"][0]["name"] == "max_length"
    assert result["data"]["common_options"][0]["name"] == "null"


def test_parse_functions(tmp_path):
    # parse_functions expects a directory containing database-functions.txt
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "database-functions.txt").write_text(
        """
.. class:: Lower(expression, **extra)

Lower
-----

Returns the lowercase form of a string.
""",
        encoding="utf-8",
    )

    output_file = tmp_path / "functions.json"
    metadata = {"sha": "123", "date": "now", "url": "local"}

    parse_functions.run(docs_dir, output_file, metadata=metadata)

    result = json.loads(output_file.read_text(encoding="utf-8"))
    assert result["data"][0]["name"] == "Lower"


def test_parse_meta(tmp_path):
    rst_file = tmp_path / "options.txt"
    rst_file.write_text(
        """
.. attribute:: Options.abstract

abstract
--------

The description.
""",
        encoding="utf-8",
    )
    output_file = tmp_path / "meta_options.json"
    metadata = {"sha": "123", "date": "now", "url": "local"}

    parse_meta.run(rst_file, output_file, metadata=metadata)

    result = json.loads(output_file.read_text(encoding="utf-8"))
    assert result["data"][0]["name"] == "abstract"
