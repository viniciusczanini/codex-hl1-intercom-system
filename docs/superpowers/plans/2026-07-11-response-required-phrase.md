# Response Required Phrase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove only “user” from the response-required announcement and publish the rebuilt phrase to `main`.

**Architecture:** The manifest remains the phrase source of truth, and the existing builder regenerates the committed WAV assets. A focused regression test locks the exact token sequence, while hash and Git-diff checks prove that the other seven WAVs remain unchanged.

**Tech Stack:** Python 3.9, `unittest`, JSON, `ffmpeg`, `ffprobe`, WAV assets, Markdown, Git.

## Global Constraints

- Final copy: “Attention. Communication required. Please acknowledge.”
- Remove only the `user` token; retain `communication` and all pauses.
- Do not change classifier, hook, queue, or configuration behavior.
- Only `assets/response_required.wav` may change among audio assets.
- Push the verified result directly to public `main`.

---

### Task 1: Lock and rebuild the exact phrase

**Files:**
- Modify: `tests/test_build_sounds.py`
- Modify: `sounds/manifest.json`
- Modify: `assets/response_required.wav`

**Interfaces:**
- Consumes: `sounds/manifest.json` through `load_manifest`.
- Produces: `response_required` tokens `attention`, `pause_sentence`, `communication`, `required`, `pause_sentence`, `please`, `acknowledge`.

- [ ] **Step 1: Write the failing regression test**

```python
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
```

- [ ] **Step 2: Run the focused test and verify RED**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_build_sounds.SoundBuilderTests.test_response_required_phrase_omits_only_user -v
```

Expected: failure showing the extra `user` token.

- [ ] **Step 3: Remove only the `user` token from the manifest**

The resulting JSON sequence must exactly match the regression test.

- [ ] **Step 4: Rebuild and prove audio isolation**

Record hashes for all assets, run `/usr/bin/python3 scripts/build_sounds.py`, and compare hashes. Require exactly one changed audio path: `assets/response_required.wav`.

- [ ] **Step 5: Run focused and full tests**

```bash
PYTHONPATH=src /usr/bin/python3 -m unittest \
  tests.test_build_sounds.SoundBuilderTests.test_response_required_phrase_omits_only_user -v
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
```

Expected: focused test and full suite pass.

### Task 2: Update displayed copy and publish

**Files:**
- Modify: `README.md`
- Modify: `INSTALLATION.md`
- Modify: `docs/superpowers/plans/2026-07-11-codex-intercom.md`

**Interfaces:**
- Produces: consistent displayed phrase in user-facing and historical design documentation.

- [ ] **Step 1: Replace the old phrase**

Replace “Attention. User communication required. Please acknowledge.” with “Attention. Communication required. Please acknowledge.” and replace “user-communication announcement” with “communication-required announcement.”

- [ ] **Step 2: Verify copy, assets, and tests**

```bash
if rg -n 'User communication required|user-communication announcement' \
  README.md INSTALLATION.md docs/superpowers; then exit 1; fi
rg -F 'Attention. Communication required. Please acknowledge.' \
  README.md INSTALLATION.md docs/superpowers/specs/2026-07-11-codex-intercom-design.md
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
git diff --check
```

Expected: obsolete copy is absent, replacement copy is present, and all tests pass.

- [ ] **Step 3: Commit and push directly**

```bash
git add README.md INSTALLATION.md sounds/manifest.json assets/response_required.wav \
  tests/test_build_sounds.py docs/superpowers
git commit -m "feat: shorten response required phrase"
git push origin main
```

- [ ] **Step 4: Verify GitHub main**

Confirm local and remote `main` hashes match, the public manifest omits only `user`, and the public `assets/response_required.wav` blob hash matches the local file.
