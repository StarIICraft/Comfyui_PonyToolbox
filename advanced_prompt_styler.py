import json
import os

from aiohttp import web


try:
    from server import PromptServer
except Exception:
    PromptServer = None


STYLES_FOLDER = "styles"
DEFAULT_STYLE_FILE = "sdxl风格提示词.json"
ROUTE_PREFIX = "/advanced_prompt_styler"


def get_styles_path():
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        STYLES_FOLDER,
    )
    os.makedirs(path, exist_ok=True)
    return path


def get_style_files():
    files = []
    for filename in os.listdir(get_styles_path()):
        path = os.path.join(get_styles_path(), filename)
        if (
            filename.lower().endswith(".json")
            and os.path.isfile(path)
        ):
            files.append(filename)

    files.sort(
        key=lambda filename: (
            filename != DEFAULT_STYLE_FILE,
            filename.casefold(),
        )
    )
    return files


def get_style_path(style_file):
    if not isinstance(style_file, str):
        return None

    filename = style_file.strip()
    if (
        not filename
        or os.path.basename(filename) != filename
        or not filename.lower().endswith(".json")
    ):
        return None

    styles_path = os.path.abspath(get_styles_path())
    path = os.path.abspath(os.path.join(styles_path, filename))

    try:
        if os.path.commonpath([styles_path, path]) != styles_path:
            return None
    except ValueError:
        return None

    if not os.path.isfile(path):
        return None
    return path


def load_styles(style_file=DEFAULT_STYLE_FILE):
    files = get_style_files()
    if style_file not in files:
        style_file = files[0] if files else DEFAULT_STYLE_FILE

    path = get_style_path(style_file)
    if path is None:
        raise ValueError(f"找不到样式文件: {style_file}")

    with open(path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"样式文件格式错误: {style_file}")

    styles = []
    seen = set()
    for item in data:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip()
        prompt = item.get("prompt")
        if not name or not isinstance(prompt, str):
            continue

        unique_name = name
        suffix = 2
        while unique_name.casefold() in seen:
            unique_name = f"{name}_{suffix}"
            suffix += 1

        seen.add(unique_name.casefold())
        styles.append(
            {
                "name": unique_name,
                "prompt": prompt,
                "negative_prompt": str(
                    item.get("negative_prompt", "") or ""
                ),
            }
        )

    if not styles:
        raise ValueError(f"样式文件没有有效条目: {style_file}")
    return styles


def get_all_style_names():
    names = []
    seen = set()
    for style_file in get_style_files():
        for style in load_styles(style_file):
            key = style["name"].casefold()
            if key not in seen:
                names.append(style["name"])
                seen.add(key)
    return names


def find_style(styles, requested_name):
    if not requested_name:
        return None

    requested = str(requested_name).strip()
    for style in styles:
        if style["name"] == requested:
            return style

    requested_casefold = requested.casefold()
    for style in styles:
        if style["name"].casefold() == requested_casefold:
            return style

    return None


class AdvancedPromptStyler:
    @classmethod
    def INPUT_TYPES(cls):
        style_files = get_style_files()
        if not style_files:
            style_files = [DEFAULT_STYLE_FILE]

        default_file = (
            DEFAULT_STYLE_FILE
            if DEFAULT_STYLE_FILE in style_files
            else style_files[0]
        )
        style_names = get_all_style_names()
        if not style_names:
            style_names = ["基础原样"]

        default_style = (
            "数字绘画"
            if "数字绘画" in style_names
            else style_names[0]
        )

        return {
            "required": {
                "text_positive": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                    },
                ),
                "text_negative": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                    },
                ),
                "style_file": (
                    style_files,
                    {
                        "default": default_file,
                    },
                ),
                "style": (
                    style_names,
                    {
                        "default": default_style,
                    },
                ),
                "log_prompt": (
                    ["No", "Yes"],
                    {
                        "default": "No",
                    },
                ),
            },
            "optional": {
                "style_name": (
                    "STRING",
                    {
                        "default": "",
                    },
                ),
            },
        }

    RETURN_TYPES = (
        "STRING",
        "STRING",
    )
    RETURN_NAMES = (
        "positive_prompt_text_g",
        "negative_prompt_text_g",
    )
    FUNCTION = "prompt_styler"
    CATEGORY = "PonyToolbox/提示词"
    DESCRIPTION = (
        "先从所选的 JSON 文件读取风格，再将风格模板应用到"
        "正向和负向提示词。"
    )

    def prompt_styler(
        self,
        text_positive,
        text_negative,
        style_file,
        style,
        log_prompt,
        style_name="",
    ):
        styles = load_styles(style_file)
        selected = find_style(styles, style_name) or find_style(styles, style)

        if selected is None:
            raise ValueError(
                f"样式文件 {style_file} 中找不到样式: {style_name or style}"
            )

        positive_prompt = selected["prompt"].replace(
            "{prompt}",
            str(text_positive or ""),
        )

        template_negative = selected["negative_prompt"].strip()
        user_negative = str(text_negative or "").strip()
        if template_negative and user_negative:
            negative_prompt = f"{template_negative}, {user_negative}"
        else:
            negative_prompt = template_negative or user_negative

        if log_prompt == "Yes":
            print(f"style_file: {style_file}")
            print(f"style: {selected['name']}")
            print(f"text_positive: {text_positive}")
            print(f"text_negative: {text_negative}")
            print(f"positive_prompt: {positive_prompt}")
            print(f"negative_prompt: {negative_prompt}")

        return positive_prompt, negative_prompt


NODE_CLASS_MAPPINGS = {
    "PonyToolboxAdvancedPromptStyler": AdvancedPromptStyler,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PonyToolboxAdvancedPromptStyler": "提示词风格器-小马",
}


def register_routes():
    if PromptServer is None:
        return

    try:
        routes = PromptServer.instance.routes
    except Exception:
        return

    @routes.get(f"{ROUTE_PREFIX}/files")
    async def api_style_files(request):
        return web.json_response(
            {
                "files": get_style_files(),
                "default": DEFAULT_STYLE_FILE,
            }
        )

    @routes.get(f"{ROUTE_PREFIX}/styles")
    async def api_styles(request):
        style_file = request.query.get("file", DEFAULT_STYLE_FILE)
        try:
            styles = load_styles(style_file)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            return web.json_response(
                {"error": str(error), "styles": []},
                status=400,
            )

        return web.json_response(
            {
                "file": style_file,
                "styles": [style["name"] for style in styles],
            }
        )


register_routes()
