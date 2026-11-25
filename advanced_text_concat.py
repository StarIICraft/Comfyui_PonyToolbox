import re


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
        return {
            "required": {
                "text1": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                    },
                ),
                "text2": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                    },
                ),
                "text3": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                    },
                ),
                "delimiter": (
                    "STRING",
                    {
                        "default": " ",
                    },
                ),
            },
            "optional": {
                "text4": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                    },
                ),
                "text5": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                    },
                ),
                "skip_empty": (
                    "BOOLEAN",
                    {
                        "default": False,
                    },
                ),
                "trim_parts": (
                    "BOOLEAN",
                    {
                        "default": False,
                    },
                ),
                "remove_empty_lines": (
                    "BOOLEAN",
                    {
                        "default": False,
                    },
                ),
                "collapse_whitespace": (
                    "BOOLEAN",
                    {
                        "default": False,
                    },
                ),
                "deduplicate": (
                    "BOOLEAN",
                    {
                        "default": False,
                    },
                ),
                "decode_escapes": (
                    "BOOLEAN",
                    {
                        "default": True,
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("concat",)
    FUNCTION = "concat"
    CATEGORY = "小马工具箱/文本"
    DESCRIPTION = (
        "合并最多五段文本，可选忽略空值、清理空白、去除空行、去重和解析转义字符。"
    )

    def concat(
        self,
        text1,
        text2,
        text3,
        delimiter,
        text4="",
        text5="",
        skip_empty=False,
        trim_parts=False,
        remove_empty_lines=False,
        collapse_whitespace=False,
        deduplicate=False,
        decode_escapes=True,
    ):
        delimiter = _flatten_text(delimiter, "")

        if decode_escapes:
            delimiter = _decode_common_escapes(delimiter)

        parts = []
        seen = set()

        for index, value in enumerate((text1, text2, text3, text4, text5)):
            part = _flatten_text(value, delimiter)

            if decode_escapes:
                part = _decode_common_escapes(part)

            if remove_empty_lines:
                part = "\n".join(
                    line for line in part.splitlines() if line.strip()
                )

            if collapse_whitespace:
                part = re.sub(r"[ \t]+", " ", part)

            if trim_parts:
                part = part.strip()

            # The first three inputs preserve ttN concat's behavior of
            # including empty values. Extra slots are only included when set.
            if index >= 3 and not part:
                continue

            if skip_empty and not part:
                continue

            if deduplicate:
                normalized = part.casefold()
                if normalized in seen:
                    continue
                seen.add(normalized)

            parts.append(part)

        return (delimiter.join(parts),)


NODE_CLASS_MAPPINGS = {
    "PonyToolboxAdvancedTextConcat": AdvancedTextConcat,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PonyToolboxAdvancedTextConcat": "高级文本拼接-小马",
}
