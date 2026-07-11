import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_sounds import load_manifest, source_url, validate_manifest


ROOT = Path(__file__).resolve().parents[1]


class SoundBuilderTests(unittest.TestCase):
    def test_response_required_phrase_omits_only_user(self):
        manifest = load_manifest(ROOT / "sounds" / "manifest.json")
        self.assertEqual(
            manifest["phrases"]["response_required"],
            [
                "attention",
                "pause_sentence",
                "communication",
                "required",
                "pause_sentence",
                "please",
                "acknowledge",
            ],
        )

    def test_every_phrase_has_a_bundled_asset(self):
        manifest = load_manifest(ROOT / "sounds" / "manifest.json")
        self.assertEqual(
            {path.stem for path in (ROOT / "assets").glob("*.wav")},
            set(manifest["phrases"]),
        )

    def test_every_phrase_references_declared_fragments(self):
        manifest = load_manifest(ROOT / "sounds" / "manifest.json")
        fragments = set(manifest["fragments"])
        for sequence in manifest["phrases"].values():
            for token in sequence:
                if not token.startswith("pause_"):
                    self.assertIn(token, fragments)

    def test_manifest_has_one_phrase_per_config_announcement(self):
        manifest = load_manifest(ROOT / "sounds" / "manifest.json")
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(manifest["phrases"]),
            set(config["announcements"]),
        )

    def test_download_url_encodes_slash(self):
        self.assertEqual(
            source_url("vox/attention.wav"),
            "https://hl1sfx.com/download/vox%2Fattention.wav",
        )

    def test_invalid_pause_token_is_rejected(self):
        manifest = {
            "fragments": {"attention": "vox/attention.wav"},
            "phrases": {"bad": ["attention", "pause_forever"]},
        }
        with self.assertRaises(ValueError):
            validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
