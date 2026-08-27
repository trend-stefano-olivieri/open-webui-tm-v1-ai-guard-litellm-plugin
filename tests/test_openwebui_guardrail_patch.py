import importlib.util
from pathlib import Path
import tempfile
import unittest


PATCH_SCRIPT = (
    Path(__file__).parents[1]
    / "patches"
    / "apply_openwebui_guardrail_denials.py"
)


def load_patch_module():
    spec = importlib.util.spec_from_file_location("openwebui_guardrail_patch", PATCH_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GuardrailDenialPatchTests(unittest.TestCase):
    def test_patch_is_applied_and_idempotent(self):
        patch = load_patch_module()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.py"
            target.write_text(f"before\n{patch.UNPATCHED}after\n")

            patch.apply_patch(target)
            self.assertIn(patch.PATCHED, target.read_text())
            self.assertNotIn(patch.UNPATCHED, target.read_text())

            patch.apply_patch(target)
            self.assertEqual(target.read_text().count(patch.PATCHED), 1)

    def test_patch_rejects_unknown_source_shape(self):
        patch = load_patch_module()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.py"
            target.write_text("unexpected upstream source\n")

            with self.assertRaises(SystemExit):
                patch.apply_patch(target)


if __name__ == "__main__":
    unittest.main()
