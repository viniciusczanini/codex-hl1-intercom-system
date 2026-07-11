# Response Required Phrase Design

## Goal

Remove only the spoken word “user” from the `response_required` announcement.

## Exact phrase

The final phrase is:

> “Attention. Communication required. Please acknowledge.”

The manifest token sequence is:

```json
[
  "attention",
  "pause_sentence",
  "communication",
  "required",
  "pause_sentence",
  "please",
  "acknowledge"
]
```

## Scope

- Update only the `response_required` sequence in `sounds/manifest.json`.
- Rebuild and commit `assets/response_required.wav`.
- Update the displayed phrase in `README.md`, `INSTALLATION.md`, and the original design specification.
- Keep classifier behavior, hook behavior, configuration keys, queue behavior, and all other WAV assets unchanged.
- Verify that only `assets/response_required.wav` changes after rebuilding.
- Push the verified result directly to public `main`.
