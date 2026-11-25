import json
import os
import re
from aiohttp import web


try:
    from server import PromptServer
except Exception:
    PromptServer = None


# ============================================================
# 配置
# ============================================================

PLUGIN_ROUTE_PREFIX = "/text_preset_selector"

PRESETS_FOLDER = "presets"

PRESET_EXTENSIONS = (".txt", ".md")

SKILL_EXTENSIONS = (".md",)

NO_PRESET = "无预设"


# ============================================================
# 路径
# ============================================================

def get_plugin_path():
    return os.path.dirname(
        os.path.abspath(__file__)
    )


def get_presets_path():
    path = os.path.join(
        get_plugin_path(),
        PRESETS_FOLDER
    )

    os.makedirs(
        path,
        exist_ok=True
    )

    return path


# ============================================================
# TXT / Markdown 文件处理
# ============================================================

def get_preset_files():
    folder = get_presets_path()

    result = []

    try:
        for filename in os.listdir(folder):
            full_path = os.path.join(
                folder,
                filename
            )

            if not os.path.isfile(full_path):
                continue

            extension = os.path.splitext(
                filename
            )[1].lower()

            if extension not in PRESET_EXTENSIONS:
                continue

            result.append(filename)

    except Exception:
        pass

    result.sort(
        key=lambda value: value.casefold()
    )

    return result


def get_txt_files():
    """兼容旧代码中的函数名。"""
    return get_preset_files()


def get_preset_name_map():
    grouped_files = {}

    for filename in get_preset_files():
        stem = os.path.splitext(
            filename
        )[0]

        grouped_files.setdefault(
            stem,
            []
        ).append(filename)

    result = {}

    for stem in sorted(
        grouped_files,
        key=lambda value: value.casefold()
    ):
        filenames = grouped_files[stem]

        if len(filenames) == 1:
            result[stem] = filenames[0]
            continue

        # 同名 TXT 保留原来的无扩展名选项，避免旧工作流失效。
        txt_files = [
            filename
            for filename in filenames
            if filename.lower().endswith(".txt")
        ]

        if txt_files:
            result[stem] = txt_files[0]

        for filename in filenames:
            if txt_files and filename == txt_files[0]:
                continue

            extension = os.path.splitext(
                filename
            )[1].lower()

            result[
                f"{stem}{extension}"
            ] = filename

    return result


def get_display_names():
    names = list(
        get_preset_name_map().keys()
    )

    if not names:
        names.append(NO_PRESET)

    return names


def get_filename(display_name):
    if display_name == NO_PRESET:
        return None

    if not isinstance(display_name, str):
        return None

    display_name = display_name.strip()

    if not display_name:
        return None

    if os.path.basename(display_name) != display_name:
        return None

    if ".." in display_name:
        return None

    name_map = get_preset_name_map()
    filename = name_map.get(display_name)

    if filename is not None:
        return filename

    # 允许直接使用带扩展名的选项，例如 foo.md。
    extension = os.path.splitext(
        display_name
    )[1].lower()

    if (
        extension in PRESET_EXTENSIONS
        and display_name in get_preset_files()
    ):
        return display_name

    return None


def get_preset_extension(display_name):
    filename = get_filename(display_name)

    if filename is None:
        return ""

    return os.path.splitext(
        filename
    )[1].lower()


def is_skill_preset(display_name):
    return (
        get_preset_extension(display_name)
        in SKILL_EXTENSIONS
    )


def read_preset(display_name):
    filename = get_filename(
        display_name
    )

    if filename is None:
        return ""

    presets_path = os.path.abspath(
        get_presets_path()
    )

    path = os.path.abspath(
        os.path.join(
            presets_path,
            filename
        )
    )

    try:
        if os.path.commonpath(
            [
                presets_path,
                path
            ]
        ) != presets_path:
            return None
    except ValueError:
        return ""

    if not os.path.isfile(path):
        return ""

    try:
        with open(
            path,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as file:
            return file.read()

    except Exception:
        return ""


def get_markdown_metadata(text):
    """读取 Markdown 中第一个 YAML 代码块的简单顶层字段。"""
    metadata = {}

    if not isinstance(text, str) or not text:
        return metadata

    blocks = re.findall(
        r"```ya?ml\s*\n(.*?)```",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not blocks:
        return metadata

    for line in blocks[0].splitlines():
        match = re.match(
            r"^\s*(name|description)\s*:\s*(.*?)\s*$",
            line,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        key = match.group(1).lower()
        value = match.group(2).strip()

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in "\"'"
        ):
            value = value[1:-1]

        if value:
            metadata[key] = value

    return metadata


def build_skill_string(display_name, text):
    text = "" if text is None else str(text)
    filename = get_filename(display_name) or ""
    metadata = get_markdown_metadata(text)

    skill_name = (
        metadata.get("name")
        or os.path.splitext(filename)[0]
        or str(display_name or "")
    )

    skill = {
        "name": skill_name,
        "instructions": text,
    }

    description = metadata.get(
        "description",
        ""
    )

    if description:
        skill["description"] = description

    if filename:
        skill["source"] = filename

    return json.dumps(
        {"skill": skill},
        ensure_ascii=False,
        indent=2,
    )


def build_preset_output(display_name, text):
    """TXT 保持原文；Markdown skill 输出 JSON 编码字符串。"""
    text = "" if text is None else str(text)

    if is_skill_preset(display_name):
        return build_skill_string(
            display_name,
            text,
        )

    return text


# ============================================================
# ComfyUI 节点
# ============================================================

class TextPresetSelector:

    @classmethod
    def INPUT_TYPES(cls):
        presets = get_display_names()

        default = presets[0]

        return {
            "required": {
                "预设": (
                    presets,
                    {
                        "default": default
                    }
                )
            }
        }

    RETURN_TYPES = (
        "STRING",
    )

    RETURN_NAMES = (
        "文本",
    )

    FUNCTION = "get_text"

    CATEGORY = "小马工具箱/文本"

    DESCRIPTION = (
        "读取 presets 中的 TXT 或 Markdown 文件。"
        "TXT 输出原文；Markdown skill 输出 JSON 字符串。"
    )

    def get_text(self, 预设):
        text = read_preset(
            预设
        )

        if text is None:
            text = ""

        return (
            build_preset_output(
                预设,
                text,
            ),
        )


# ============================================================
# 节点注册
# ============================================================

NODE_CLASS_MAPPINGS = {
    "PonyToolboxTextPresetSelector": TextPresetSelector,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "PonyToolboxTextPresetSelector": "文本预设-小马",
}


# ============================================================
# API
# ============================================================

def register_routes():
    if PromptServer is None:
        return

    try:
        routes = (
            PromptServer
            .instance
            .routes
        )

    except Exception:
        return

    @routes.get(
        f"{PLUGIN_ROUTE_PREFIX}/presets"
    )
    async def api_presets(request):
        return web.json_response({
            "presets": get_display_names()
        })

    @routes.get(
        f"{PLUGIN_ROUTE_PREFIX}/content"
    )
    async def api_content(request):
        preset = request.query.get(
            "preset",
            ""
        )

        text = read_preset(preset) or ""

        return web.json_response({
            "text": text,
            "output": build_preset_output(
                preset,
                text,
            ),
            "is_skill": is_skill_preset(preset),
        })


register_routes()
