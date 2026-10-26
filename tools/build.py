"""Build a source distribution with an explicit, auditable file allowlist."""

import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from FaderPort_Follow import __version__  # noqa: E402


PUBLIC_DOCS = (
    "docs/ARCHITECTURE.md",
    "docs/CURVE_FIT.md",
    "docs/PROJECT_GUIDE.md",
    "docs/RELEASE_NOTES.md",
    "docs/VALIDATION.md",
    "docs/validation-results.json",
)


def distribution_files():
    paths = [ROOT / name for name in ("README.md", "Install.ps1", "Uninstall.ps1", "LICENSE", "COPYRIGHT")]
    paths.extend(ROOT / name for name in PUBLIC_DOCS)
    for folder in ("FaderPort_Follow", "tests", "tools"):
        paths.extend(path for path in (ROOT / folder).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts
                     and path.suffix in (".py", ".psm1", ".ps1"))
    return sorted(set(paths))


def build(output=None):
    output = Path(output) if output else ROOT / "dist"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ("FaderPort_Follow-%s.zip" % __version__)
    manifest = {"version": __version__, "files": {}}
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in distribution_files():
            data = path.read_bytes()
            relative = path.relative_to(ROOT).as_posix()
            # Fixed timestamps make identical inputs produce identical archives.
            member = zipfile.ZipInfo(relative, (2026, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            member.external_attr = 0o644 << 16
            bundle.writestr(member, data)
            manifest["files"][relative] = hashlib.sha256(data).hexdigest()
        member = zipfile.ZipInfo("MANIFEST.json", (2026, 1, 1, 0, 0, 0))
        member.compress_type = zipfile.ZIP_DEFLATED
        member.external_attr = 0o644 << 16
        bundle.writestr(member, json.dumps(manifest, indent=2, ensure_ascii=False))
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(checksum + "  " + archive.name + "\n", encoding="utf-8")
    return archive


if __name__ == "__main__":
    print(build())

