# Anki Deck Template

Build with Python:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python build.py
```

Import `dist/deck.apkg` into Anki. Commit `deck.json` after the first local build, but never change the generated namespace.

## Edit

- `notes.tsv`: edit notes; `subdeck_id` is subdeck number from `deck.json` or use `_` for the main deck
- `deck.json`: edit deck names
- `templates/`: edit cards and CSS (fields come from TSV headers)
- `media/`: add media files; reference using `<img src="photo.jpg">` or `[sound:audio.mp3]` in notes

Use `<br>` for line breaks. Rename already-imported decks in Anki too.
Keep note and subdeck IDs permanent, never reuse them.

## Release

Pushes/PRs build an artifact. Publish a release:

```sh
git tag v1.0.0
git push origin v1.0.0
```
