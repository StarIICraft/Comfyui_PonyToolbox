import re


MAX_TEXT_INPUTS = 32

_ESCAPE_PATTERN = re.compile(r"\\(n|r|t|\\)")
_ESCAPE_REPLACEMENTS = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "\\": "\\",
}


def _decode_common_escapes(value):
    return _ESCAPE_PATTERN.sub(
        lambda match: _ESCAPE_REPLACEMENTS[match.group(1)],
        value,
    )


def _flatten_text(value, delimiter):
    if value is None:
        return ""

    if isinstance(value, (list, tuple)):
        return delimiter.join(
            part
            for part in (_flatten_text(item, delimiter) for item in value)
            if part
        )

    if value == "undefined":
        return ""

    return str(value)


class AdvancedTextConcat:
    @classmethod
    def INPUT_TYPES(cls):
        optional = {
            f"text{index}": (
                "STRING",
                {
                    "default": "",
                    "multiline": True,
                },
            )
            for index in range(1, MAX_TEXT_INPUTS + 1)
        }
        optional["delimiter"] = (
            "STRING",
            {
                "default": " ",
            },
        )
        optional["decode_escapes"] = (
            "BOOLEAN",
            {
                "default": True,
            },
        )

        return {
            "optional": optional,
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("concat",)
    FUNCTION = "concat"
    CATEGORY = "小马工具箱/文本"
    DESCRIPTION = (
        "连接文本行并以分隔符合并；默认显示两行，可在节点内动态增加，支持解析转义字符。"
    )

    def concat(
        self,
        delimiter=" ",
        decode_escapes=True,
        **kwargs,
    ):
        delimiter = _flatten_text(delimiter, "")

        if decode_escapes:
            delimiter = _decode_common_escapes(delimiter)

        values = [
            kwargs.get(f"text{index}", "")
            for index in range(1, MAX_TEXT_INPUTS + 1)
        ]

        parts = []

        for value in values:
            part = _flatten_text(value, delimiter)

            if decode_escapes:
                part = _decode_common_escapes(part)

            if not part:
                continue

            parts.append(part)

        return (delimiter.join(parts),)


NODE_CLASS_MAPPINGS = {
    "PonyToolboxAdvancedTextConcat": AdvancedTextConcat,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PonyToolboxAdvancedTextConcat": "高级文本拼接-小马",
}
