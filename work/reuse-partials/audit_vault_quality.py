"""Scoped file-link and current-entry checks for a reviewed vault maintenance round.

These checks validate navigation and symbol presence, not runtime behavior.
The caller supplies the canonical/staged overlay; this module writes nothing.
"""
import ast
import posixpath
import re
from pathlib import PurePosixPath
from urllib.parse import unquote


def audit(read, exists, review):
    scoped = review['scoped_notes']
    assert scoped and len(scoped) == len(set(scoped))
    count = 0
    for note in scoped:
        assert exists(note), note
        for href in re.findall(r'\]\(([^)]+)\)', read(note)):
            href = unquote(href.strip('<>').split('#', 1)[0])
            if not href or '://' in href or re.match(r'^[A-Z]:', href, re.I):
                continue
            target = posixpath.normpath(str(PurePosixPath(note).parent / href))
            assert not target.startswith('../') and exists(target), (note, href)
            count += 1
    symbols = review['existing_entry_symbols']
    assert symbols
    for name, expected in symbols.items():
        actual = {node.name for node in ast.walk(ast.parse(read(name)))
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert expected and set(expected) <= actual, (name, expected - actual if isinstance(expected, set) else expected)
    return dict(scoped_notes=scoped, local_file_links_checked=count,
                broken_file_links=[], existing_entry_symbols=symbols)
