import csv
import hashlib
import html
import json
import os
import re
import sys
import uuid
from html.parser import HTMLParser
from pathlib import Path

import genanki

ROOT = Path(__file__).resolve().parent


def anki_id(namespace, key):
    value = json.dumps([namespace, key]).encode("utf-8")
    return int(hashlib.sha256(value).hexdigest()[:13], 16) + 1


class MediaReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names = set()

    def handle_starttag(self, tag, attrs):
        if tag in {"img", "audio", "source", "video"}:
            for key, value in attrs:
                if key in {"src", "poster"} and value:
                    self.names.add(value)


def media_names(text):
    parser = MediaReferences()
    parser.feed(text)
    parser.names.update(re.findall(r"\[sound:([^\]]+)\]", text))
    parser.names.update(
        match[1].strip() for match in re.findall(r"url\(\s*(['\"]?)(.*?)\1\s*\)", text)
    )
    return {html.unescape(name) for name in parser.names}


def build():
    config_path = ROOT / "deck.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    initialize = config.get("guid_namespace") in (None, "")
    if initialize and os.environ.get("CI", "").lower() == "true":
        raise ValueError(
            "One-time setup required: deck.json has no guid_namespace.\n"
            "CI cannot save a permanent namespace for future builds.\n\n"
            "After installing the dependencies (see README), run locally from the repository root:\n"
            "  python build.py\n"
            "  git add deck.json\n"
            '  git commit -m "Initialize deck namespace"\n'
            "  git push\n\n"
            "The push will trigger a new build. Keep the saved namespace unchanged."
        )
    if initialize:
        config["guid_namespace"] = uuid.uuid4().hex
    namespace = config["guid_namespace"]
    if not isinstance(namespace, str) or not namespace or namespace != namespace.strip():
        raise ValueError("guid_namespace must be nonempty with no surrounding spaces")
    name = config["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError("deck name must not be empty")
    subdecks = config.get("subdecks", {})
    ids = list(subdecks.values())
    if any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("subdeck IDs must be unique positive integers")
    if any(not part.strip() for name in subdecks for part in name.split("::")):
        raise ValueError("subdeck names must have nonempty components")

    with (ROOT / "notes.tsv").open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t", quoting=csv.QUOTE_NONE)
        columns = reader.fieldnames or []
        missing = {"id", "subdeck_id"} - set(columns)
        if missing:
            raise ValueError("missing required columns: " + ", ".join(sorted(missing)))
        if len(columns) != len(set(columns)):
            raise ValueError("duplicate column names")
        if any(not name or name != name.strip() for name in columns):
            raise ValueError("column names must be nonempty with no surrounding spaces")
        fields = [name for name in columns if name not in {"id", "subdeck_id"}]
        if not fields:
            raise ValueError("notes.tsv must contain at least one card field")
        rows = [(reader.line_num, row) for row in reader]

    front, back, css = [
        (ROOT / "templates" / name).read_text(encoding="utf-8")
        for name in ("front.html", "back.html", "style.css")
    ]
    model = genanki.Model(
        anki_id(namespace, "model"), name + " Basic",
        fields=[{"name": field} for field in fields],
        templates=[{"name": "Card 1", "qfmt": front, "afmt": back}], css=css,
    )
    decks = {"_": genanki.Deck(anki_id(namespace, "deck"), name)}
    for subdeck, id_ in subdecks.items():
        decks[str(id_)] = genanki.Deck(anki_id(namespace, f"subdeck:{id_}"), f"{name}::{subdeck}")
    seen = set()
    media = media_names(front + "\n" + back + "\n" + css)
    for line_num, row in rows:
        where = f"notes.tsv:{line_num}"
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{where}: wrong number of columns")
        note_id = row["id"]
        if not re.fullmatch(r"[1-9][0-9]*", note_id):
            raise ValueError(f"{where}: id must be a positive integer without leading zeros")
        if note_id in seen:
            raise ValueError(f"{where}: duplicate id {note_id!r}")
        seen.add(note_id)
        guid = genanki.guid_for(namespace, note_id)
        subdeck_id = row["subdeck_id"]
        if subdeck_id not in decks:
            raise ValueError(f"{where}: unknown subdeck ID {subdeck_id!r}; use a configured ID or '_'")
        values = [row[field] for field in fields]
        decks[subdeck_id].add_note(genanki.Note(model=model, fields=values, guid=guid))
        for value in values:
            media.update(media_names(value))

    paths = []
    for name in sorted(media):
        if name.startswith(("https://", "http://", "//", "data:")):
            continue
        if name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError(f"media references must be filenames only: {name!r}")
        path = ROOT / "media" / name
        if not path.is_file():
            raise ValueError(f"missing media: media/{name}")
        paths.append(str(path))
    if initialize:
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        print("Saved guid_namespace; commit deck.json and keep the namespace unchanged.")
    output = ROOT / "dist" / "deck.apkg"
    output.parent.mkdir(exist_ok=True)
    genanki.Package(list(decks.values()), media_files=paths).write_to_file(str(output))
    print(f"Built {output}: {len(seen)} notes, {len(paths)} media files")


if __name__ == "__main__":
    try:
        build()
    except (ValueError, KeyError, OSError) as error:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            message = str(error).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error title=Deck build failed::{message}", flush=True)
        sys.exit(f"Build failed: {error}")
