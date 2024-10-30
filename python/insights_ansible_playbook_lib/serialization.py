import logging
import typing

import yaml.parser
import yaml.scanner
import yaml.composer


logger = logging.getLogger(__name__)


__all__ = ["Loader", "serialize_play"]


class CustomSafeConstructor(yaml.constructor.SafeConstructor):
    def construct_yaml_bool(self, node: "yaml.ScalarNode"):  # type: ignore
        value = self.construct_scalar(node)
        if str(value).lower() not in ("true", "false"):
            return value
        return super().construct_yaml_bool(node)

    def construct_yaml_int(self, node: "yaml.ScalarNode"):  # type: ignore
        value = self.construct_scalar(node)
        if ":" not in str(value):
            return super().construct_yaml_int(node)
        return value


class Loader(
    yaml.reader.Reader,
    yaml.scanner.Scanner,
    yaml.parser.Parser,
    yaml.composer.Composer,
    CustomSafeConstructor,
    yaml.resolver.Resolver,
):
    def __init__(self, stream: str):
        yaml.reader.Reader.__init__(self, stream)
        yaml.scanner.Scanner.__init__(self)
        yaml.parser.Parser.__init__(self)
        yaml.composer.Composer.__init__(self)
        CustomSafeConstructor.__init__(self)
        yaml.resolver.Resolver.__init__(self)

        type(self).add_constructor(
            "tag:yaml.org,2002:bool", CustomSafeConstructor.construct_yaml_bool
        )  # type: ignore
        type(self).add_constructor(
            "tag:yaml.org,2002:int", CustomSafeConstructor.construct_yaml_int
        )  # type: ignore


class Serializer:
    @classmethod
    def _obj(cls, value: typing.Any) -> str:
        if isinstance(value, dict):
            return cls._dict(value)
        if isinstance(value, list):
            return cls._list(value)
        if isinstance(value, int) or isinstance(value, float):
            return str(value)
        if isinstance(value, str):
            return cls._str(value)
        logger.debug(f"Value type unknown: {value} {type(value).__name__}")
        return f"'{value}'"

    @classmethod
    def _dict(cls, source: dict) -> str:
        result = "ordereddict(["
        result += ", ".join(
            "('{key}', {value})".format(key=k, value=cls._obj(v))
            for k, v in source.items()
        )
        result += "])"
        return result

    @classmethod
    def _list(cls, source: list) -> str:
        result = "["
        result += ", ".join(cls._obj(v) for v in source)
        result += "]"
        return result

    @classmethod
    def _str(cls, value: str) -> str:
        # no quote      'no quote'
        # single'quote  "single'quote"
        # double"quote  'double"quote'
        # both"'quotes  'both"\'quotes'

        quote: str = "'"
        if "'" in value:
            if '"' not in value:
                quote = '"'
            else:
                value = value.replace("'", "\\'")

        return quote + value + quote


def serialize_play(play: dict) -> str:
    return Serializer._obj(play)
