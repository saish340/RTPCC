"""CSRNet crowd-density inference and one-image visual sanity check.

Download the official ShanghaiTech Part B checkpoint to, for example,
``models/partBmodel_best.pth.tar`` before running this script:
https://drive.google.com/file/d/1zKn6YlLW3Z9ocgPbP99oz7r2nC7_TBXK/view

Install the optional vision dependencies first (see pyproject.toml), then run:
    python scripts/csrnet_infer.py --weights models/partBmodel_best.pth.tar \
        --image path/to/test.jpg --output artifacts/csrnet_overlay.png

``predict_density_map`` accepts an OpenCV-style BGR frame and returns a float32
map at exactly the same height and width.  Its sum is preserved from the native
CSRNet (1/8-resolution) output, so it is the model's frame-level person count.
"""

from __future__ import annotations

import argparse
import os
import pickle
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as functional


# These are the channel means used by the official CSRNet validation notebook.
# Frames are converted BGR -> RGB before the values are subtracted.
CSRNET_RGB_MEAN = (92.8207477031, 95.2757037428, 104.877445883)


def make_layers(
    configuration: list[int | str],
    in_channels: int = 3,
    *,
    dilation: bool = False,
) -> nn.Sequential:
    """Build the frontend/backend used by the authors' PyTorch implementation."""
    dilation_rate = 2 if dilation else 1
    layers: list[nn.Module] = []
    for value in configuration:
        if value == "M":
            layers.append(nn.MaxPool2d(kernel_size=2, stride=2))
            continue
        convolution = nn.Conv2d(
            in_channels,
            int(value),
            kernel_size=3,
            padding=dilation_rate,
            dilation=dilation_rate,
        )
        layers.extend((convolution, nn.ReLU(inplace=True)))
        in_channels = int(value)
    return nn.Sequential(*layers)


class CSRNet(nn.Module):
    """CSRNet architecture compatible with the official checkpoint state dict."""

    def __init__(self) -> None:
        super().__init__()
        self.frontend = make_layers([64, 64, "M", 128, 128, "M", 256, 256, 256, "M", 512, 512, 512])
        self.backend = make_layers([512, 512, 512, 256, 128, 64], in_channels=512, dilation=True)
        self.output_layer = nn.Conv2d(64, 1, kernel_size=1)

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return self.output_layer(self.backend(self.frontend(image)))


def _checkpoint_state_dict(checkpoint: object) -> dict[str, torch.Tensor]:
    """Accept both the official checkpoint dict and a raw state dictionary."""
    if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
        checkpoint = checkpoint["state_dict"]
    if not isinstance(checkpoint, dict):
        raise ValueError("CSRNet checkpoint must be a state dict or contain a 'state_dict' key.")
    state_dict = {str(key).removeprefix("module."): value for key, value in checkpoint.items()}
    if not all(isinstance(value, torch.Tensor) for value in state_dict.values()):
        raise ValueError("Checkpoint state dict contains non-tensor values.")
    return state_dict


def load_model(weights_path: str | Path) -> CSRNet:
    """Load official CSRNet Part B weights onto CUDA when available, otherwise CPU."""
    path = Path(weights_path)
    # Creating this directory makes the documented destination usable on a
    # fresh checkout; the missing checkpoint itself still fails clearly below.
    os.makedirs(path.parent, exist_ok=True)
    if not path.is_file():
        raise FileNotFoundError(
            f"CSRNet weights not found: {path}\n"
            "Download partBmodel_best.pth.tar from the URL in this file's docstring."
        )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    try:
        checkpoint = torch.load(path, map_location=device, weights_only=True)
    except TypeError:  # Supports older PyTorch releases that lack weights_only.
        checkpoint = torch.load(path, map_location=device)
    except pickle.UnpicklingError:
        # The official CSRNet 2018 checkpoint predates PyTorch's safe
        # weights-only format. Only use this fallback for a checkpoint obtained
        # from the official CSRNet source named in this file's docstring.
        checkpoint = torch.load(path, map_location=device, weights_only=False)
    model = CSRNet()
    model.load_state_dict(_checkpoint_state_dict(checkpoint), strict=True)
    model.to(device).eval()
    # Keep the public signature small while allowing predict_density_map to use
    # precisely the same device selected during loading.
    model._csrnet_device = device  # type: ignore[attr-defined]
    return model


def predict_density_map(model: CSRNet, frame: np.ndarray) -> np.ndarray:
    """Return a count-preserving, full-frame density map for a BGR video frame.

    The native CSRNet output is 1/8 of the input size. It is bilinearly resized
    to frame coordinates, then rescaled so the sum remains the native predicted
    person count. This makes polygon masking in Step B geometrically direct.
    """
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame must be an HxWx3 BGR numpy array.")
    height, width = frame.shape[:2]
    if height < 8 or width < 8:
        raise ValueError("frame must be at least 8x8 pixels for CSRNet.")

    # Avoid importing OpenCV in the core wrapper: RGB conversion is simple and
    # keeps this function usable with any numpy-backed image source.
    rgb = np.ascontiguousarray(frame[:, :, ::-1])
    tensor = torch.from_numpy(rgb).permute(2, 0, 1).float()
    for channel, mean in enumerate(CSRNET_RGB_MEAN):
        tensor[channel].sub_(mean)
    device = getattr(model, "_csrnet_device", next(model.parameters()).device)

    with torch.inference_mode():
        native = model(tensor.unsqueeze(0).to(device))
        native_count = native.sum()
        full_size = functional.interpolate(native, size=(height, width), mode="bilinear", align_corners=False)
        resized_sum = full_size.sum()
        if float(resized_sum.abs()) > 1e-12:
            full_size = full_size * (native_count / resized_sum)

    return full_size[0, 0].detach().cpu().numpy().astype(np.float32, copy=False)


def save_overlay(frame: np.ndarray, density_map: np.ndarray, output_path: str | Path) -> None:
    """Write a BGR frame with a colour density heatmap overlay for visual review."""
    import cv2

    if density_map.shape != frame.shape[:2]:
        raise ValueError("density_map must match the frame height and width.")
    positive_density = np.maximum(density_map, 0)
    maximum = float(np.percentile(positive_density, 99.5))
    normalized = np.zeros_like(positive_density, dtype=np.uint8)
    if maximum > 0:
        normalized = np.clip(positive_density / maximum * 255, 0, 255).astype(np.uint8)
    heatmap = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(frame, 0.58, heatmap, 0.42, 0)
    path = Path(output_path)
    os.makedirs(path.parent, exist_ok=True)
    if not cv2.imwrite(str(path), overlay):
        raise OSError(f"Could not write heatmap overlay to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CSRNet on one image and save a density-map overlay.")
    parser.add_argument("--weights", required=True, help="Path to official partBmodel_best.pth.tar")
    parser.add_argument("--image", required=True, help="Test image path")
    parser.add_argument("--output", default="artifacts/csrnet_overlay.png", help="Output PNG path")
    args = parser.parse_args()

    import cv2

    frame = cv2.imread(args.image, cv2.IMREAD_COLOR)
    if frame is None:
        raise SystemExit(f"Could not read test image: {args.image}")
    try:
        model = load_model(args.weights)
        density_map = predict_density_map(model, frame)
        save_overlay(frame, density_map, args.output)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"CSRNet inference failed: {exc}") from exc

    print(f"Image: {args.image} ({frame.shape[1]}x{frame.shape[0]})")
    print(f"Estimated people: {float(density_map.sum()):.2f}")
    print(f"Density-map overlay: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
