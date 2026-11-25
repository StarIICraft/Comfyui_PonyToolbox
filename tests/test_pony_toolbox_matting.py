import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


PLUGIN_ROOT = Path(
    os.environ.get(
        "PONY_TOOLBOX_ROOT",
        Path(__file__).resolve().parents[1],
    )
)
sys.path.insert(0, str(PLUGIN_ROOT))

from pony_toolbox_mask import (  # noqa: E402
    adjust_mask,
    mask_offset_pixels,
    mask_percent_to_pixels,
    offset_then_feather,
)


def _load_matting_node():
    torch = types.ModuleType("torch")
    comfy = types.ModuleType("comfy")
    comfy.__path__ = []
    model_management = types.ModuleType("comfy.model_management")
    model_patcher = types.ModuleType("comfy.model_patcher")
    model_patcher.ModelPatcher = type("ModelPatcher", (), {})
    folder_paths = types.ModuleType("folder_paths")
    folder_paths.models_dir = str(PLUGIN_ROOT / "models")

    sys.modules.setdefault("torch", torch)
    sys.modules.setdefault("comfy", comfy)
    sys.modules.setdefault("comfy.model_management", model_management)
    sys.modules.setdefault("comfy.model_patcher", model_patcher)
    sys.modules.setdefault("folder_paths", folder_paths)

    spec = importlib.util.spec_from_file_location(
        "pony_toolbox_matting_under_test",
        PLUGIN_ROOT / "pony_toolbox_matting.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MaskPercentTests(unittest.TestCase):
    def test_percent_uses_area_equivalent_length(self):
        self.assertAlmostEqual(
            mask_percent_to_pixels(1024, 1024, 0.1),
            1.024,
        )
        self.assertAlmostEqual(
            mask_percent_to_pixels(1920, 1080, 0.1),
            1.44,
        )
        self.assertAlmostEqual(
            mask_percent_to_pixels(4096, 4096, 0.07),
            2.8672,
        )

    def test_effective_radius_is_capped_at_64_pixels(self):
        self.assertEqual(mask_percent_to_pixels(16384, 16384, 1.0), 64.0)

    def test_nonzero_offset_rounds_to_at_least_one_pixel(self):
        self.assertEqual(mask_offset_pixels(512, 512, -0.1), -1)
        self.assertEqual(mask_offset_pixels(1024, 1024, 0.0001), 1)
        self.assertEqual(mask_offset_pixels(1920, 1080, -1.0), -14)
        self.assertEqual(mask_offset_pixels(4096, 4096, 1.0), 41)
        self.assertEqual(mask_offset_pixels(1024, 1024, 0), 0)

    def test_offset_is_applied_before_feather(self):
        mask = Image.new("L", (9, 9), 0)
        ImageDraw.Draw(mask).rectangle((2, 2, 6, 6), fill=255)

        actual = offset_then_feather(mask, -1, 1.5)
        expected = mask.filter(ImageFilter.MinFilter(3)).filter(
            ImageFilter.GaussianBlur(1.5)
        )
        reverse = mask.filter(ImageFilter.GaussianBlur(1.5)).filter(
            ImageFilter.MinFilter(3)
        )

        np.testing.assert_array_equal(np.asarray(actual), np.asarray(expected))
        self.assertFalse(np.array_equal(np.asarray(actual), np.asarray(reverse)))

    def test_adjust_mask_uses_percentage_inputs(self):
        mask = Image.new("L", (5, 5), 0)
        mask.putpixel((2, 2), 255)

        adjusted = adjust_mask(mask, 1.0, 0.0, 0.0, False)

        np.testing.assert_array_equal(np.asarray(adjusted), np.asarray(mask))


class MattingNodeSchemaTests(unittest.TestCase):
    def test_percentage_mask_inputs_and_defaults(self):
        node = _load_matting_node()
        required = node.PonyToolboxMatting.INPUT_TYPES()["required"]

        self.assertNotIn("mask_blur", required)
        self.assertNotIn("mask_offset", required)
        self.assertEqual(required["mask_offset_percent"][0], "FLOAT")
        self.assertEqual(required["mask_feather_percent"][0], "FLOAT")

        offset = required["mask_offset_percent"][1]
        feather = required["mask_feather_percent"][1]
        self.assertEqual(offset["default"], -0.1)
        self.assertEqual(offset["min"], -1.0)
        self.assertEqual(offset["max"], 1.0)
        self.assertEqual(offset["step"], 0.01)
        self.assertEqual(feather["default"], 0.07)
        self.assertEqual(feather["min"], 0.0)
        self.assertEqual(feather["max"], 1.0)
        self.assertEqual(feather["step"], 0.01)

    def test_native_key_layout_is_preserved_when_supported(self):
        node = _load_matting_node()
        key = (
            "bb.encoder.layers.0.blocks.0."
            "attention.q_proj.weight"
        )
        source = {
            key: types.SimpleNamespace(shape=(4, 4)),
        }

        result, report = node._adapt_feynobg_state_dict(
            source,
            {key: (4, 4)},
            {key},
            lambda state_dict: state_dict,
        )

        self.assertIs(result[key], source[key])
        self.assertEqual(report["layout"], "native")

    def test_modern_swin_keys_are_adapted_to_current_target(self):
        node = _load_matting_node()
        tensor = types.SimpleNamespace(shape=(4, 4))
        source = {
            "bb.swin.encoder.layers.0.blocks.0.attention.q_proj.weight":
                tensor,
        }
        remap_calls = []

        result, report = node._adapt_feynobg_state_dict(
            source,
            {
                "bb.encoder.layers.0.blocks.0."
                "attention.self.query.weight": (4, 4),
            },
            {
                "bb.encoder.layers.0.blocks.0."
                "attention.self.query.weight",
            },
            lambda state_dict: remap_calls.append(state_dict) or state_dict,
        )

        self.assertIn(
            "bb.encoder.layers.0.blocks.0."
            "attention.self.query.weight",
            result,
        )
        self.assertEqual(report["layout"], "swin")
        self.assertEqual(remap_calls, [])

    def test_legacy_feynobg_state_dict_is_remapped(self):
        node = _load_matting_node()
        source = {
            "bb.patch_embed.proj.weight":
                types.SimpleNamespace(shape=(4, 4)),
        }
        remapped = {
            "bb.swin.encoder.layers.0.blocks.0."
            "attention.q_proj.weight":
                types.SimpleNamespace(shape=(4, 4)),
        }

        result, report = node._adapt_feynobg_state_dict(
            source,
            {
                "bb.encoder.layers.0.blocks.0."
                "attention.self.query.weight": (4, 4),
            },
            {
                "bb.encoder.layers.0.blocks.0."
                "attention.self.query.weight",
            },
            lambda state_dict: remapped,
        )

        self.assertIn(
            "bb.encoder.layers.0.blocks.0."
            "attention.self.query.weight",
            result,
        )
        self.assertEqual(report["layout"], "legacy")

    def test_root_swin_layernorm_is_safely_ignored(self):
        node = _load_matting_node()
        source = {
            "bb.swin.layernorm.weight":
                types.SimpleNamespace(shape=(4,)),
        }

        result, report = node._adapt_feynobg_state_dict(
            source,
            {},
            set(),
            lambda state_dict: state_dict,
        )

        self.assertEqual(result, {})
        self.assertEqual(
            report["ignored"],
            ["bb.swin.layernorm.weight"],
        )

    def test_missing_parameter_is_rejected(self):
        node = _load_matting_node()

        with self.assertRaisesRegex(RuntimeError, "缺少参数"):
            node._adapt_feynobg_state_dict(
                {},
                {"decoder.conv.weight": (4, 4)},
                {"decoder.conv.weight"},
                lambda state_dict: state_dict,
            )


if __name__ == "__main__":
    unittest.main()
