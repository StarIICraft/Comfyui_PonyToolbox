from contextlib import contextmanager
from pathlib import Path
import json
import re
import sys
import threading
import types

import numpy as np
from PIL import Image
import torch

import comfy.model_management as model_management
from comfy.model_patcher import ModelPatcher
import folder_paths

try:
    from .pony_toolbox_mask import adjust_mask
except ImportError:
    from pony_toolbox_mask import adjust_mask


MODEL_PATHS = {
    "INSPYRENET": Path("RMBG") / "INSPYRENET" / "inspyrenet.pth",
    "FeyNoBg": Path("RMBG") / "FeyNoBg" / "FeyNobg.safetensors",
}
MODEL_LABELS = {
    "INSPYRENET 抠图": "INSPYRENET",
    "FeyNoBg 抠图": "FeyNoBg",
}
MEMORY_KEEP = "保持模型加载"
MEMORY_UNLOAD = "每次运行后卸载"
BACKGROUND_ALPHA = "透明背景"
BACKGROUND_COLOR = "纯色背景"
MODEL_RESOLUTION = 1024

_MODEL_CACHE = {
    "key": None,
    "backend": None,
    "patcher": None,
    "remover": None,
    "model": None,
    "processor": None,
}
_MODEL_LOCK = threading.RLock()


@contextmanager
def _without_pymatting():
    saved = {}
    for name in list(sys.modules):
        if name == "pymatting" or name.startswith("pymatting."):
            saved[name] = sys.modules[name]
            del sys.modules[name]

    package = types.ModuleType("pymatting")
    package.__path__ = []
    foreground = types.ModuleType("pymatting.foreground")
    foreground.__path__ = []
    sys.modules["pymatting"] = package
    sys.modules["pymatting.foreground"] = foreground
    try:
        yield
    finally:
        for name in list(sys.modules):
            if name == "pymatting" or name.startswith("pymatting."):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


@contextmanager
def _without_albumentations():
    """
    Import transparent_background without its optional Albumentations path.

    INSPYRENET receives PIL images from this node, so Remover only uses its
    torchvision path. Stubbing Albumentations avoids incompatible
    albumentations/albucore combinations installed by other custom nodes.
    """
    prefixes = (
        "albumentations",
        "albucore",
        "transparent_background",
    )
    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in prefixes
        )
    }
    for name in saved:
        sys.modules.pop(name, None)

    albumentations = types.ModuleType("albumentations")
    albumentations.__path__ = []
    albumentations.Resize = lambda *args, **kwargs: None
    albumentations.Normalize = lambda *args, **kwargs: None
    albumentations.Compose = lambda *args, **kwargs: None

    albumentations_pytorch = types.ModuleType(
        "albumentations.pytorch"
    )
    albumentations_pytorch.__path__ = []
    albumentations_pytorch.ToTensorV2 = (
        lambda *args, **kwargs: None
    )

    albumentations_core = types.ModuleType("albumentations.core")
    albumentations_core.__path__ = []
    transforms_interface = types.ModuleType(
        "albumentations.core.transforms_interface"
    )
    transforms_interface.ImageOnlyTransform = object

    albumentations.pytorch = albumentations_pytorch
    albumentations.core = albumentations_core
    albumentations_core.transforms_interface = transforms_interface

    sys.modules["albumentations"] = albumentations
    sys.modules["albumentations.pytorch"] = (
        albumentations_pytorch
    )
    sys.modules["albumentations.core"] = albumentations_core
    sys.modules[
        "albumentations.core.transforms_interface"
    ] = transforms_interface
    try:
        yield
    finally:
        for name in list(sys.modules):
            if any(
                name == prefix or name.startswith(prefix + ".")
                for prefix in prefixes
            ):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def _tensor_to_pil(image):
    array = (
        image[..., :3]
        .detach()
        .to(device="cpu", dtype=torch.float32)
        .clamp(0, 1)
        .mul(255)
        .round()
        .to(torch.uint8)
        .numpy()
    )
    return Image.fromarray(array, mode="RGB")


def _pil_to_image_tensor(image):
    array = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def _mask_to_tensor(mask):
    array = np.asarray(mask, dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def _mask_image_tensor(mask):
    array = np.asarray(mask.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def _unload_model(patcher):
    keep_loaded = [
        loaded
        for loaded in model_management.current_loaded_models
        if loaded.model is not patcher
    ]
    model_management.free_memory(
        1e30,
        patcher.load_device,
        keep_loaded=keep_loaded,
    )
    model_management.soft_empty_cache()


def _load_inspyrenet(model_path):
    with _without_albumentations(), _without_pymatting():
        from transparent_background.Remover import Remover

        remover = Remover(ckpt=str(model_path), device="cpu")
    return remover, remover.model, None


_FEYNOBG_IGNORABLE_KEY = re.compile(
    r"^(?:(?:bb(?:\.swin)?|model\.bb(?:\.swin)?)"
    r"\.layernorm\.(?:weight|bias))$"
)


def _modern_to_legacy_swin_key(key):
    key = key.replace(
        ".attention.q_proj.",
        ".attention.self.query.",
    )
    key = key.replace(
        ".attention.k_proj.",
        ".attention.self.key.",
    )
    key = key.replace(
        ".attention.v_proj.",
        ".attention.self.value.",
    )
    key = key.replace(
        ".attention.o_proj.",
        ".attention.output.dense.",
    )
    key = key.replace(
        ".attention.relative_position_bias."
        "relative_position_bias_table",
        ".attention.self.relative_position_bias_table",
    )
    key = key.replace(".mlp.fc1.", ".intermediate.dense.")
    key = key.replace(".mlp.fc2.", ".output.dense.")
    return key


def _legacy_to_modern_swin_key(key):
    key = key.replace(
        ".attention.self.query.",
        ".attention.q_proj.",
    )
    key = key.replace(
        ".attention.self.key.",
        ".attention.k_proj.",
    )
    key = key.replace(
        ".attention.self.value.",
        ".attention.v_proj.",
    )
    key = key.replace(
        ".attention.output.dense.",
        ".attention.o_proj.",
    )
    key = key.replace(
        ".attention.self.relative_position_bias_table",
        ".attention.relative_position_bias."
        "relative_position_bias_table",
    )
    key = key.replace(".intermediate.dense.", ".mlp.fc1.")
    key = key.replace(".output.dense.", ".mlp.fc2.")
    return key


def _feynobg_key_candidates(key):
    prefixes = [key]
    for prefix in ("model.", "module."):
        if key.startswith(prefix):
            prefixes.append(key[len(prefix):])

    expanded = []
    for name in prefixes:
        if name.startswith("bb.swin."):
            expanded.append("bb." + name[len("bb.swin."):])
        elif name.startswith("bb.") and not name.startswith("bb.swin."):
            expanded.append("bb.swin." + name[len("bb."):])
        expanded.append(name)

    candidates = []
    for name in expanded:
        for candidate in (
            name,
            _modern_to_legacy_swin_key(name),
            _legacy_to_modern_swin_key(name),
        ):
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _adapt_feynobg_state_dict(
    state_dict,
    target_shapes,
    target_parameter_names,
    remap_legacy,
):
    is_legacy = any(
        name.startswith("bb.patch_embed.")
        for name in state_dict
    )
    prepared = remap_legacy(state_dict) if is_legacy else state_dict
    adapted = {}
    ignored = []
    unmatched = []

    for source_key, value in prepared.items():
        shape = tuple(value.shape)
        target_key = next(
            (
                candidate
                for candidate in _feynobg_key_candidates(source_key)
                if (
                    candidate in target_shapes
                    and target_shapes[candidate] == shape
                )
            ),
            None,
        )
        if target_key is None:
            if (
                "relative_position_index" in source_key
                or _FEYNOBG_IGNORABLE_KEY.fullmatch(source_key)
            ):
                ignored.append(source_key)
                continue
            unmatched.append(source_key)
            continue
        if target_key in adapted:
            raise RuntimeError(
                "FeyNoBg 权重存在重复目标键："
                f"{target_key}"
            )
        adapted[target_key] = value

    required_names = set(target_parameter_names)
    missing_parameters = sorted(
        required_names - adapted.keys()
    )
    if unmatched or missing_parameters:
        details = []
        if unmatched:
            details.append(
                f"未匹配键 {len(unmatched)} 个：{unmatched[:5]}"
            )
        if missing_parameters:
            details.append(
                "缺少参数 "
                f"{len(missing_parameters)} 个："
                f"{missing_parameters[:5]}"
            )
        raise RuntimeError(
            "FeyNoBg 权重布局无法安全适配当前 Swin 模型；"
            + "；".join(details)
        )

    return adapted, {
        "layout": (
            "legacy"
            if is_legacy
            else "swin"
            if any(
                name.startswith("bb.swin.")
                for name in state_dict
            )
            else "native"
        ),
        "matched": len(adapted),
        "ignored": ignored,
    }


def _load_feynobg(model_path):
    from .pony_toolbox_feynobg.birefnet.modeling_birefnet import (
        BiRefNet,
        BiRefNetConfig,
        _remap_legacy_state_dict,
    )
    from safetensors.torch import load_file

    model_dir = model_path.parent
    config_data = json.loads(
        (model_dir / "config.json").read_text(encoding="utf-8")
    )
    model = BiRefNet(BiRefNetConfig(**config_data))
    target_state = model.state_dict()
    target_parameter_names = {
        name
        for name, _parameter in model.named_parameters()
    }
    try:
        state_dict, report = _adapt_feynobg_state_dict(
            load_file(str(model_path)),
            {
                name: tuple(value.shape)
                for name, value in target_state.items()
            },
            target_parameter_names,
            _remap_legacy_state_dict,
        )
        load_result = model.load_state_dict(
            state_dict,
            strict=False,
        )
        missing_parameters = sorted(
            set(load_result.missing_keys)
            & target_parameter_names
        )
        if missing_parameters or load_result.unexpected_keys:
            raise RuntimeError(
                "加载结果不完整："
                f"缺少参数={missing_parameters[:5]}，"
                f"额外键={load_result.unexpected_keys[:5]}"
            )
    except RuntimeError as error:
        raise RuntimeError(
            f"FeyNoBg 权重与当前模型结构不兼容：{error}"
        ) from error
    print(
        "[Pony Toolbox] FeyNoBg state_dict adapted: "
        f"layout={report['layout']} "
        f"matched={report['matched']} "
        f"ignored={len(report['ignored'])}"
    )
    model.eval()
    if torch.cuda.is_available():
        model = model.half()
    processor = json.loads(
        (model_dir / "preprocessor_config.json").read_text(encoding="utf-8")
    )
    return None, model, processor


def _load_backend(backend, model_path):
    load_device = model_management.get_torch_device()
    key = (backend, str(model_path), str(load_device))

    with _MODEL_LOCK:
        if _MODEL_CACHE["key"] != key:
            old_patcher = _MODEL_CACHE["patcher"]
            if old_patcher is not None:
                _unload_model(old_patcher)

            if backend == "INSPYRENET":
                remover, model, processor = _load_inspyrenet(model_path)
            else:
                remover, model, processor = _load_feynobg(model_path)

            patcher = ModelPatcher(
                model,
                load_device=load_device,
                offload_device=model_management.unet_offload_device(),
            )
            _MODEL_CACHE.update(
                key=key,
                backend=backend,
                patcher=patcher,
                remover=remover,
                model=model,
                processor=processor,
            )

        patcher = _MODEL_CACHE["patcher"]
        model_management.load_models_gpu([patcher])
        if backend == "INSPYRENET":
            remover = _MODEL_CACHE["remover"]
            remover.model = patcher.model
            remover.device = load_device
        return patcher, _MODEL_CACHE["remover"], patcher.model, _MODEL_CACHE["processor"]


def _make_mask(source, backend, model, remover, processor):
    if backend == "INSPYRENET":
        width, height = source.size
        aspect = height / width
        resized = source.resize(
            (MODEL_RESOLUTION, max(1, int(MODEL_RESOLUTION * aspect))),
            Image.Resampling.LANCZOS,
        )
        prediction = remover.process(resized, type="map").convert("L")
        return prediction.resize(source.size, Image.Resampling.LANCZOS)

    width = int(processor["size"]["width"])
    height = int(processor["size"]["height"])
    resized = source.resize((width, height), Image.Resampling.BILINEAR)
    values = np.asarray(resized, dtype=np.float32)
    values = values * float(processor["rescale_factor"])
    values = (
        values - np.asarray(processor["image_mean"], dtype=np.float32)
    ) / np.asarray(processor["image_std"], dtype=np.float32)
    pixel_values = torch.from_numpy(values).permute(2, 0, 1).unsqueeze(0).to(
        device=next(model.parameters()).device,
        dtype=next(model.parameters()).dtype,
    )
    with torch.no_grad():
        outputs = model(pixel_values=pixel_values)
    alpha = outputs["logits"] if isinstance(outputs, dict) else outputs.logits
    alpha = torch.nn.functional.interpolate(
        alpha.sigmoid(),
        size=(source.height, source.width),
        mode="bilinear",
        align_corners=False,
    )[0, 0]
    alpha = alpha.detach().cpu().float().clamp(0, 1).numpy()
    return Image.fromarray(
        np.round(alpha * 255.0).astype(np.uint8),
        mode="L",
    )


def _composite(source, mask, refine_foreground, background, background_color):
    foreground = source
    if refine_foreground:
        from .pony_toolbox_feynobg.utils import refine_foreground as refine_alpha

        foreground = refine_alpha(source, mask)

    if background == BACKGROUND_ALPHA:
        output = Image.new("RGBA", source.size, (0, 0, 0, 0))
        output.paste(foreground, (0, 0), mask)
        return output

    color = background_color.lstrip("#")
    if len(color) != 6:
        color = "222222"
    rgb = tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))
    output = Image.new("RGB", source.size, rgb)
    output.paste(foreground, (0, 0), mask)
    return output


class PonyToolboxMatting:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "backend": (
                    ["INSPYRENET 抠图", "FeyNoBg 抠图"],
                    {"default": "INSPYRENET 抠图", "tooltip": "选择本地抠图模型后端。"},
                ),
                "image": ("IMAGE", {"tooltip": "需要去除背景的图像批次。"}),
                "sensitivity": (
                    "FLOAT",
                    {
                        "default": 1.0,
                        "min": 0.1,
                        "max": 3.0,
                        "step": 0.05,
                        "tooltip": "调整遮罩对比度；1.0 保持模型原始预测。",
                    },
                ),
                "mask_offset_percent": (
                    "FLOAT",
                    {
                        "default": -0.1,
                        "min": -1.0,
                        "max": 1.0,
                        "step": 0.01,
                        "tooltip": "按图像百万像素等效边长调整遮罩；正数扩张，负数收缩。",
                    },
                ),
                "mask_feather_percent": (
                    "FLOAT",
                    {
                        "default": 0.07,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.01,
                        "tooltip": "先偏移再羽化；按图像百万像素等效边长计算高斯半径。",
                    },
                ),
                "invert_output": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "反转最终遮罩。"},
                ),
                "refine_foreground": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "细化发丝和半透明边缘的前景颜色，减少旧背景光晕。",
                    },
                ),
                "background": (
                    [BACKGROUND_ALPHA, BACKGROUND_COLOR],
                    {
                        "default": BACKGROUND_ALPHA,
                        "tooltip": "透明背景输出 RGBA；纯色背景会把主体合成到指定颜色。",
                    },
                ),
                "background_color": (
                    "STRING",
                    {
                        "default": "#222222",
                        "tooltip": "纯色背景使用的十六进制颜色，例如 #222222。",
                    },
                ),
                "memory_policy": (
                    [MEMORY_KEEP, MEMORY_UNLOAD],
                    {
                        "default": MEMORY_KEEP,
                        "tooltip": "保持加载可加快连续运行；每次卸载会释放显存并允许 ComfyUI 清理机制接管。",
                    },
                ),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "IMAGE")
    RETURN_NAMES = ("图像", "遮罩", "遮罩图像")
    FUNCTION = "remove_background"
    CATEGORY = "小马工具箱/图像"
    DESCRIPTION = (
        "使用本地 INSPYRENET 或 FeyNoBg 模型抠图，输出 RGBA/纯色背景图像、"
        "遮罩和遮罩预览。模型会注册到 ComfyUI 模型管理器。"
    )

    def remove_background(
        self,
        backend="INSPYRENET 抠图",
        image=None,
        sensitivity=1.0,
        mask_offset_percent=-0.1,
        mask_feather_percent=0.07,
        invert_output=False,
        refine_foreground=True,
        background=BACKGROUND_ALPHA,
        background_color="#222222",
        memory_policy=MEMORY_KEEP,
    ):
        backend_name = MODEL_LABELS[backend]
        model_path = Path(folder_paths.models_dir) / MODEL_PATHS[backend_name]
        if not model_path.is_file():
            raise FileNotFoundError(f"找不到 {backend_name} 模型：{model_path}")
        if backend_name == "FeyNoBg" and not model_path.with_name("config.json").is_file():
            raise FileNotFoundError(f"找不到 FeyNoBg 配置：{model_path.parent / 'config.json'}")

        patcher, remover, model, processor = _load_backend(backend_name, model_path)
        try:
            output_images = []
            masks = []
            mask_images = []
            for item in image:
                source = _tensor_to_pil(item)
                mask = _make_mask(
                    source,
                    backend_name,
                    model,
                    remover,
                    processor,
                )
                mask = adjust_mask(
                    mask,
                    sensitivity,
                    mask_offset_percent,
                    mask_feather_percent,
                    invert_output,
                )
                output = _composite(
                    source,
                    mask,
                    refine_foreground,
                    background,
                    background_color,
                )
                output_images.append(_pil_to_image_tensor(output))
                masks.append(_mask_to_tensor(mask))
                mask_images.append(_mask_image_tensor(mask))
        finally:
            if memory_policy == MEMORY_UNLOAD:
                _unload_model(patcher)

        return (
            torch.cat(output_images, dim=0),
            torch.cat(masks, dim=0),
            torch.cat(mask_images, dim=0),
        )


NODE_CLASS_MAPPINGS = {
    "PonyToolboxMatting": PonyToolboxMatting,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PonyToolboxMatting": "抠图-小马",
}
