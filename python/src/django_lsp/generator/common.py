"""
Common utilities for Django documentation parsers.
"""

import re


def clean_rst_markup(text: str) -> str:
    """Convert RST markup to markdown-ish format."""
    # Convert RST inline code to markdown
    text = re.sub(r"``([^`]+)``", r"`\1`", text)
    # Convert RST references to plain text or links
    text = re.sub(r":setting:`([^`<]+)`", r"`\1`", text)
    text = re.sub(r":setting:`[^<]*<([^>]+)>`", r"`\1`", text)
    text = re.sub(r":lookup:`([^`<]+)`", r"`\1`", text)
    text = re.sub(r":class:`~?([^`]+)`", r"`\1`", text)
    text = re.sub(r":meth:`~?([^`]+)`", r"`\1()`", text)
    text = re.sub(r":exc:`~?([^`]+)`", r"`\1`", text)
    text = re.sub(r":ref:`([^`<]+)`", r"\1", text)
    text = re.sub(r":ref:`[^<]*<([^>]+)>`", r"\1", text)
    text = re.sub(r":doc:`[^<]*<([^>]+)>`", r"\1", text)
    text = re.sub(r":doc:`([^`]+)`", r"\1", text)
    text = re.sub(r":mod:`([^`]+)`", r"`\1`", text)
    text = re.sub(r":func:`([^`]+)`", r"`\1()`", text)
    text = re.sub(r":attr:`([^`]+)`", r"`\1`", text)
    text = re.sub(r":tfilter:`[^<]*<([^>]+)>`", r"\1", text)
    text = re.sub(r":tfilter:`([^`]+)`", r"\1", text)

    # Remove .. directives and their content if they are block-level
    text = re.sub(
        r"\.\. (?:versionchanged|versionadded|deprecated|admonition|warning|note|tip|important|caution)::[^\n]*\n*(?:    [^\n]*(?:\n|$))*",
        "",
        text,
    )

    # Handle direct text blocks (remove directives but keep indentation if it's a code block)
    # This line is now redundant due to the change above, but keeping it as per instruction to only make the requested change.
    text = re.sub(
        r"\.\. (?:admonition|warning|note|tip|important|caution)::\s*\n", "", text
    )

    # Clean up external links
    text = re.sub(r"`([^`]+)`_", r"\1", text)
    text = re.sub(r"\.\. _[^:]+: https?://[^\n]+\n?", "", text)

    return text.strip()


def extract_code_example(text: str) -> str:
    """Extract code example from RST text."""
    # Look for code blocks (lines after :: or .. code-block::)
    code_blocks = []
    lines = text.split("\n")
    in_code_block = False
    code_indent = 4
    current_block = []

    for line in lines:
        if not in_code_block:
            if line.rstrip().endswith("::") or ".. code-block::" in line:
                in_code_block = True
                current_block = []
                continue
        else:
            if not line.strip():
                if current_block:
                    current_block.append("")
                continue

            # Use the indentation of the first non-empty line
            if not current_block:
                code_indent = len(line) - len(line.lstrip())
                if code_indent == 0:  # Not actually indented, end of block
                    in_code_block = False
                    continue

            if (len(line) - len(line.lstrip())) < code_indent:
                # End of code block
                if current_block:
                    code_blocks.append("\n".join(current_block).strip())
                in_code_block = False
                current_block = []
            else:
                current_block.append(line[code_indent:])

    if current_block:
        code_blocks.append("\n".join(current_block).strip())

    # Return the first substantial code block
    for block in code_blocks:
        if len(block.strip()) > 10:
            return block.strip()

    return ""


def slugify(name: str) -> str:
    """Convert a name to a URL slug."""
    return name.lower().replace("_", "-")


def strip_trailing_pointers(text: str) -> str:
    """Remove trailing sentences that point to other documentation sections."""
    patterns = [
        r"The following .* are available.*",
        r"See below for .*",
        r"Example::",
        r"Here's an example with .*",
        r"Here's a setup that .*",
        r"For more info, see .*",
    ]

    for pattern in patterns:
        text = re.sub(rf"\n*{pattern}\s*$", "", text, flags=re.IGNORECASE | re.DOTALL)

    return text.strip()
