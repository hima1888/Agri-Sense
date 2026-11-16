"""One-off: convert the two Hugging Face disease models to ONNX and verify them.

NOT part of the application. Run it in a separate, throwaway virtual environment:

    python -m venv /tmp/convert && /tmp/convert/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
    /tmp/convert/bin/pip install transformers safetensors onnx onnxruntime huggingface_hub
    /tmp/convert/bin/python scripts/convert_disease_models.py --out backend/ml_models

What it does (see docs/DISEASE_MODELS.md):
* downloads both models' safetensors weights (for PlantVillage: HF's conversion-bot PR #2) and checks
  them bit-for-bit against the original pickle, which is opened only with ``weights_only=True``;
* exports opset-17 ONNX with a dynamic batch axis and runs ``onnx.checker``;
* compares ONNX Runtime logits with PyTorch on random inputs.
The app checks the resulting files against the SHA-256 values in app/vision/disease.py.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
from transformers import MobileNetV2ForImageClassification, ViTForImageClassification

VIT = "wambugu71/crop_leaf_diseases_vit"
PV = "linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification"


def fetch(repo: str, files: list[str], folder: Path, revision: str | None = None) -> None:
    for f in files:
        hf_hub_download(repo, f, local_dir=folder, revision=revision)


def export(cls: type, folder: Path, out: Path) -> dict[str, object]:
    model = cls.from_pretrained(folder, use_safetensors=True).eval()
    torch.onnx.export(
        model,
        (torch.randn(1, 3, 224, 224),),
        out,
        input_names=["pixel_values"],
        output_names=["logits"],
        dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )
    onnx.checker.check_model(onnx.load(out))
    session = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    xs = torch.randn(8, 3, 224, 224) * 1.2
    with torch.no_grad():
        ref = model(pixel_values=xs).logits.numpy()
    got = session.run(None, {"pixel_values": xs.numpy()})[0]
    out.with_suffix(".labels.json").write_text(json.dumps(model.config.id2label, indent=0))
    return {
        "max_abs_logit_diff": float(np.abs(ref - got).max()),
        "argmax_agree": int((ref.argmax(1) == got.argmax(1)).sum()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work", type=Path, default=Path("hf_download"))
    args = ap.parse_args()
    torch.manual_seed(0)
    vit, pv, ref = args.work / "vit", args.work / "pv", args.work / "pv_ref"
    fetch(VIT, ["config.json", "preprocessor_config.json", "model.safetensors"], vit)
    fetch(PV, ["config.json", "preprocessor_config.json"], pv)
    fetch(PV, ["model.safetensors"], pv, revision="refs/pr/2")
    fetch(PV, ["pytorch_model.bin"], ref)

    st = load_file(pv / "model.safetensors")
    pickled = torch.load(ref / "pytorch_model.bin", map_location="cpu", weights_only=True)
    assert set(st) == set(pickled), "safetensors and pickle have different tensors"
    assert all(torch.equal(st[k], pickled[k]) for k in st), "safetensors differ from the original pickle"

    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        "crop_leaf_vit": export(ViTForImageClassification, vit, args.out / "crop_leaf_vit.onnx"),
        "plantvillage_mnv2": export(
            MobileNetV2ForImageClassification, pv, args.out / "plantvillage_mnv2.onnx"
        ),
    }
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
