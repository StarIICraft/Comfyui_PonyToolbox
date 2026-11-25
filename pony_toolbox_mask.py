import math

import numpy as np
from PIL import Image, ImageFilter, ImageOps


MAX_EFFECTIVE_RADIUS_PX = 64.0


def mask_percent_to_pixels(width, height, percent):
    reference_length = math.sqrt(max(1, int(width)) * max(1, int(height)))
    radius = reference_length * float(percent) / 100.0
    return min(abs(radius), MAX_EFFECTIVE_RADIUS_PX)


def mask_offset_pixels(width, height, percent):
    percent = float(percent)
    if percent == 0:
        return 0

    radius = mask_percent_to_pixels(width, height, percent)
    rounded = int(math.floor(radius + 0.5))
    rounded = max(1, rounded)
    return rounded if percent > 0 else -rounded


def offset_then_feather(mask, offset_px, feather_px):
    if offset_px:
        size = abs(int(offset_px)) * 2 + 1
        filter_type = ImageFilter.MaxFilter if offset_px > 0 else ImageFilter.MinFilter
        mask = mask.filter(filter_type(size))

    if feather_px > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(float(feather_px)))
    return mask


def adjust_mask(
    mask,
    sensitivity,
    offset_percent,
    feather_percent,
    invert_output,
):
    if sensitivity != 1.0:
        values = np.asarray(mask, dtype=np.float32)
        values = np.clip((values - 127.5) * sensitivity + 127.5, 0, 255)
        mask = Image.fromarray(values.astype(np.uint8), mode="L")

    offset_px = mask_offset_pixels(mask.width, mask.height, offset_percent)
    feather_px = mask_percent_to_pixels(
        mask.width,
        mask.height,
        feather_percent,
    )
    mask = offset_then_feather(mask, offset_px, feather_px)

    if invert_output:
        mask = ImageOps.invert(mask)
    return mask
