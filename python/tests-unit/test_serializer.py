import sys

import pytest

from insights_ansible_playbook_lib import serialization


class TestPlaybookSerializer:
    def test_list(self):
        source = ["a", "b"]
        result = serialization.Serializer._list(source)
        expected = "['a', 'b']"
        assert result == expected

    def test_dict_empty_value(self):
        source = {"a": None}
        result = serialization.Serializer._dict(source)
        expected = "ordereddict([('a', None)])"
        assert result == expected

    def test_dict_single(self):
        source = {"a": "a"}
        result = serialization.Serializer._dict(source)
        expected = "ordereddict([('a', 'a')])"
        assert result == expected

    def test_dict_list(self):
        source = {"a": ["a1", "a2"]}
        result = serialization.Serializer._dict(source)
        expected = "ordereddict([('a', ['a1', 'a2'])])"
        assert result == expected

    def test_dict_mixed(self):
        source = {"a": "a", "b": ["b1", "b2"]}
        result = serialization.Serializer._dict(source)
        expected = "ordereddict([('a', 'a'), ('b', ['b1', 'b2'])])"
        assert result == expected

    def test_dict_multiple(self):
        source = {"a": "a", "b": "b"}
        result = serialization.Serializer._dict(source)
        expected = "ordereddict([('a', 'a'), ('b', 'b')])"
        assert result == expected

    def test_numbers(self):
        source = {"integer": 37, "float": 17.93233901}
        result = serialization.Serializer._dict(source)
        expected = "ordereddict([('integer', 37), ('float', 17.93233901)])"
        assert result == expected

    @pytest.mark.parametrize(
        "source,expected",
        [
            ("no quote", "'no quote'"),
            ("single'quote", '''"single'quote"'''),
            ('double"quote', """'double"quote'"""),
            ("both\"'quotes", r"""'both"\'quotes'"""),
            ("\\backslash", "'\\\\backslash'"),
            ("new\nline", "'new\\nline'"),
            ("tab\tchar", "'tab\\tchar'"),
        ],
    )
    def test_strings(self, source, expected):
        result = serialization.Serializer._str(source)
        assert result == expected

    def test_strings_emoji_zwj(self):
        if sys.version_info >= (3, 12):
            raise pytest.xfail("CCT-644")

        source = "👨🏼‍🚀"
        result = serialization.Serializer._str(source)

        expected = "'👨🏼\u200d🚀'"
        assert result == expected
