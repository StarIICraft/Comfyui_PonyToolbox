# Compatibility shim for ComfyUI's Transformers 4.x environment.
# The FeyNoBg node only uses the BiRefNet model and its local processor.

from .birefnet.modeling_birefnet import BiRefNet, BiRefNetConfig

__version__ = "0.3.1"
