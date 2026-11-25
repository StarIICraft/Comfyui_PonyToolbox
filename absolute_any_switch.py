class AnyType(str):
    def __ne__(self, __value: object) -> bool:
        return False


ANY_TYPE = AnyType("*")


def is_empty_switch_value(value):
    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, (dict, list, tuple, set)):
        return len(value) == 0

    return False


class AbsoluteAnySwitch:
    """
    更严格的任意类型切换节点。

    前端会在提交工作流前只保留第一个有效分支；开启
    allow_muted_upstream 时，静音或旁路分支会先沿同类型
    输入解析到可执行来源。后端再跳过 None、空字符串和
    空集合。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "allow_muted_upstream": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": (
                            "开启后，允许静音、旁路或禁用节点"
                            "沿上游传递有效值；默认关闭。"
                        ),
                    },
                ),
                **{
                    f"any_{index:02d}": (
                        ANY_TYPE,
                        {
                            "tooltip": (
                                "按输入编号顺序选择第一个有效值。"
                                "静音、旁路和禁用分支会被跳过。"
                            ),
                        },
                    )
                    for index in range(1, 17)
                },
            },
        }

    RETURN_TYPES = (ANY_TYPE,)
    RETURN_NAMES = ("输出",)
    FUNCTION = "switch"
    CATEGORY = "小马工具箱/流程"

    DESCRIPTION = (
        "兼容原任意切换的输入顺序，"
        "并正确跳过静音、旁路、禁用和空值分支；"
        "需要兼容静音上游时可显式开启对应选项。"
    )

    def switch(self, allow_muted_upstream=False, **kwargs):
        for index in range(1, 17):
            value = kwargs.get(f"any_{index:02d}")

            if not is_empty_switch_value(value):
                return (value,)

        return (None,)


NODE_CLASS_MAPPINGS = {
    "PonyToolboxAbsoluteAnySwitch": AbsoluteAnySwitch,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "PonyToolboxAbsoluteAnySwitch": "绝对任意切换-小马",
}
