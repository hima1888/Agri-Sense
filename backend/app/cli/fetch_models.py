"""Download the recognition model and labels, and verify the model checksum.

python -m app.cli.fetch_models
"""

import hashlib
import sys
import urllib.request

from app.vision.recognizer import LABEL_FILE, LABEL_SOURCE, MODEL_DIR, MODEL_FILE, MODEL_SHA256, MODEL_SOURCE


def main() -> int:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for url, path in ((MODEL_SOURCE, MODEL_FILE), (LABEL_SOURCE, LABEL_FILE)):
        if path.is_file():
            print(f"exists: {path.name}")
            continue
        print(f"downloading {url}")
        urllib.request.urlretrieve(url, path)  # noqa: S310 - fixed https URLs
    digest = hashlib.sha256(MODEL_FILE.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        MODEL_FILE.unlink()
        print(f"checksum mismatch ({digest}); file removed", file=sys.stderr)
        return 1
    print("model verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
