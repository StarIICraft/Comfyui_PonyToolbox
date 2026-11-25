from .text_preset_selector import (
    build_preset_output,
    get_display_names,
    read_preset,
)


class EnhancedTextPresetSelector:

    @classmethod
    def INPUT_TYPES(cls):
        presets = get_display_names()

        default_preset = presets[0]

        default_text = read_preset(
            default_preset
        )

        if default_text is None:
            default_text = ""

        return {
            "required": {
                "预设": (
                    presets,
                    {
                        "default": default_preset
                    }
                ),

                "临时编辑文本": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": default_text,
                        "forceInput": False,
                        "defaultInput": False
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
        "编辑框显示 TXT 或 Markdown 原文。"
        "TXT 输出原文；Markdown skill 输出 JSON 字符串。"
    )

    def get_text(
        self,
        预设,
        临时编辑文本
    ):
        return (
            build_preset_output(
                预设,
                临时编辑文本,
            ),
        )


NODE_CLASS_MAPPINGS = {
    "PonyToolboxEnhancedTextPresetSelector": EnhancedTextPresetSelector,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "PonyToolboxEnhancedTextPresetSelector": "增强文本预设-小马",
}
