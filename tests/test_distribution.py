import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET

from tools.build import ROOT, build


class DistributionTests(unittest.TestCase):
    def test_archive_allowlist_manifest_checksum_and_reproducibility(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as temporary, \
                tempfile.TemporaryDirectory(dir=ROOT / "docs") as local_notes:
            notes = Path(local_notes)
            (notes / "private.md").write_text("Local notes must stay private.", encoding="utf-8")
            (notes / "private.json").write_text('{"scope": "local"}', encoding="utf-8")
            archive = build(temporary)
            first = archive.read_bytes()
            with zipfile.ZipFile(archive) as bundle:
                names = bundle.namelist()
                self.assertIn("FaderPort_Follow/__init__.py", names)
                self.assertIn("tools/Installation.psm1", names)
                self.assertIn("docs/VALIDATION.md", names)
                self.assertIn("docs/RELEASE_NOTES.md", names)
                self.assertIn("COPYRIGHT", names)
                self.assertNotIn("AGENTS.local.md", names)
                published_docs = {name for name in names if name.startswith("docs/")}
                self.assertEqual(published_docs, {
                    "docs/ARCHITECTURE.md", "docs/CURVE_FIT.md",
                    "docs/PROJECT_GUIDE.md", "docs/RELEASE_NOTES.md",
                    "docs/VALIDATION.md", "docs/validation-results.json",
                })
                self.assertNotIn("docs/figures/faderport-regression.png", names)
                self.assertNotIn("docs/figures/faderport-regression.svg", names)
                self.assertFalse(any("tmp/" in name or "__pycache__" in name or name.endswith(".pdf") for name in names))
                manifest = json.loads(bundle.read("MANIFEST.json"))
                self.assertIn("GNU GENERAL PUBLIC LICENSE", bundle.read("LICENSE").decode("utf-8"))
                self.assertIn("GPL-3.0-or-later", bundle.read("COPYRIGHT").decode("utf-8"))
                for name in names:
                    if name.endswith((".md", ".json", ".py", ".ps1", ".psm1")):
                        self.assertNotRegex(bundle.read(name).decode("utf-8"), r"[\u4e00-\u9fff]")
                for name, digest in manifest["files"].items():
                    self.assertEqual(hashlib.sha256(bundle.read(name)).hexdigest(), digest)
                self.assertEqual(set(names), set(manifest["files"]) | {"MANIFEST.json"})
                self.assertTrue(all(info.date_time == (2026, 1, 1, 0, 0, 0) for info in bundle.infolist()))
            self.assertEqual(archive.with_suffix(".zip.sha256").read_text().split()[0], hashlib.sha256(first).hexdigest())
            self.assertEqual(first, build(temporary).read_bytes())


@unittest.skipUnless(sys.platform == "win32" and shutil.which("powershell"), "Windows PowerShell required")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.library = Path(self.temporary.name) / "Library [test] & spaces"
        self.library.mkdir()
        self.target = self.library / "Remote Scripts" / "FaderPort_Follow"
        self.sentinel = self.library / "unrelated.txt"
        self.sentinel.write_text("keep", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def run_script(self, script, *args, expected=0):
        result = subprocess.run([shutil.which("powershell"), "-NoProfile", "-ExecutionPolicy", "Bypass",
                                 "-File", str(ROOT / script), "-UserLibrary", str(self.library), *args],
                                capture_output=True, encoding="utf-8", errors="replace", timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_install_upgrade_restore_uninstall_preserve_other_files(self):
        self.run_script("Install.ps1")
        self.assertTrue((self.target / "surface.py").is_file())
        self.assertFalse((self.target / "__pycache__").exists())
        custom = self.target / "personal-note.txt"
        custom.write_text("old settings", encoding="utf-8")
        self.run_script("Install.ps1")
        self.assertFalse(custom.exists())
        marker = json.loads((self.target / ".faderport-follow-install.json").read_text(encoding="utf-8-sig"))
        backup = Path(marker["previousBackup"])
        self.assertEqual((backup / custom.name).read_text(), "old settings")
        self.run_script("Uninstall.ps1", "-RestorePrevious")
        self.assertEqual(custom.read_text(), "old settings")
        self.run_script("Uninstall.ps1")
        self.assertFalse(self.target.exists())
        self.assertEqual(self.sentinel.read_text(), "keep")
        self.run_script("Uninstall.ps1")

    def test_restore_path_outside_backup_root_is_rejected_before_mutation(self):
        self.run_script("Install.ps1")
        marker_path = self.target / ".faderport-follow-install.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8-sig"))
        marker["previousBackup"] = str(self.library)
        marker_path.write_text(json.dumps(marker), encoding="utf-8")
        self.run_script("Uninstall.ps1", "-RestorePrevious", expected=1)
        self.assertTrue((self.target / "surface.py").exists())
        self.assertEqual(self.sentinel.read_text(), "keep")

    def test_manual_install_is_not_removed_by_uninstaller(self):
        self.target.mkdir(parents=True)
        (self.target / "custom.py").write_text("keep", encoding="utf-8")
        self.run_script("Uninstall.ps1", expected=1)
        self.assertEqual((self.target / "custom.py").read_text(), "keep")

    def test_autodetection_joins_project_name_and_chooses_latest_live_version(self):
        appdata = Path(self.temporary.name) / "Fake AppData"
        for version, folder in (("12.4.6", "Old Library"), ("12.4.7", "User Library")):
            library = self.library / folder
            library.mkdir()
            root = ET.Element("Ableton")
            project = ET.SubElement(ET.SubElement(ET.SubElement(root, "ContentLibrary"), "UserLibrary"), "LibraryProject")
            ET.SubElement(project, "ProjectPath", Value=str(self.library))
            ET.SubElement(project, "ProjectName", Value=folder)
            config = appdata / "Ableton" / ("Live " + version) / "Preferences" / "Library.cfg"
            config.parent.mkdir(parents=True)
            ET.ElementTree(root).write(config, encoding="utf-8", xml_declaration=True)
        result = subprocess.run([shutil.which("powershell"), "-NoProfile", "-Command",
            "Import-Module '.\\tools\\Installation.psm1' -Force; Get-FollowLibrary"],
            cwd=ROOT, env=dict(os.environ, APPDATA=str(appdata)), capture_output=True,
            encoding="utf-8", errors="replace", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.library / "User Library"))

    def test_debug_switch_changes_only_installed_settings(self):
        original = (ROOT / 'FaderPort_Follow' / 'settings.py').read_bytes()
        self.run_script('Install.ps1', '-DebugMidi')
        self.assertIn('DEBUG_MIDI = True', (self.target / 'settings.py').read_text())
        self.assertEqual((ROOT / 'FaderPort_Follow' / 'settings.py').read_bytes(), original)
