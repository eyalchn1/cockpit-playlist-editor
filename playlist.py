"""Lossless Cockpit document and a separate display projection."""
import json
import ntpath
import os
import re
import tempfile
from decimal import Decimal
from dataclasses import dataclass
from pathlib import Path


SONG_EXTENSIONS = (".wrk", ".mid", ".midi")
SONG_FILE_FILTER = "Song files (" + " ".join(
    pattern for extension in SONG_EXTENSIONS for pattern in ("*" + extension, "*" + extension.upper())
) + ");;All files (*)"


def song_name_key(path):
    return tuple((1, int(part)) if part.isdigit() else (0, part)
                 for part in re.split(r"(\d+)", path.name.casefold())), path.name


@dataclass(frozen=True)
class DisplayEntry:
    index: int
    name: str
    number: int | None
    category: bool


class Playlist:
    def __init__(self, data: dict, source: Path | None):
        if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
            raise ValueError("נדרש אובייקט JSON עם מערך entries")
        for index, entry in enumerate(data["entries"]):
            if not isinstance(entry, dict):
                raise ValueError(f"entry {index + 1} אינו אובייקט")
            if "is_category" in entry and not isinstance(entry["is_category"], bool):
                raise ValueError(f"is_category בפריט {index + 1} חייב להיות boolean")
            for field in ("title", "path"):
                if field in entry and not isinstance(entry[field], str):
                    raise ValueError(f"{field} בפריט {index + 1} חייב להיות טקסט")
        self.data = data
        self.source = source

    @classmethod
    def load(cls, filename):
        source = Path(filename)
        with source.open(encoding="utf-8-sig") as stream:
            return cls(json.load(stream, parse_float=Decimal), source.resolve())

    def save(self, filename):
        """Serialize all data, then atomically replace the destination file."""
        destination = Path(filename).resolve()
        content = encode_json(self.data) + "\n"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                    dir=destination.parent, prefix=".cockpit-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        self.source = destination

    @property
    def name(self):
        return str(self.data.get("name") or (self.source.stem if self.source else "Untitled"))

    def import_folders(self, folders, index):
        """Read direct children only; stage the entire import before changing entries."""
        if not 0 <= index <= len(self.data["entries"]):
            raise ValueError("Invalid insertion index")
        staged = Playlist({"entries": []}, None)
        for folder in folders:
            folder = Path(folder).resolve()
            songs = sorted((path for path in folder.iterdir()
                            if path.is_file() and path.suffix.casefold() in SONG_EXTENSIONS),
                           key=song_name_key)
            staged.insert_entry(len(staged.data["entries"]), category_name=folder.name)
            for song in songs:
                staged.insert_entry(len(staged.data["entries"]), song_path=str(song))
        self.data["entries"][index:index] = staged.data["entries"]

    def display_entries(self):
        result = []
        number = 0
        for index, entry in enumerate(self.data["entries"]):
            category = entry.get("is_category", False)
            if category:
                name = entry.get("title") or "קטגוריה ללא שם"
            else:
                number += 1
                name = ntpath.splitext(ntpath.basename(entry.get("path", "")))[0]
                name = name or entry.get("title") or "שיר ללא שם"
            result.append(DisplayEntry(index, name, None if category else number, category))
        return result

    def move_songs(self, indices, boundary):
        """Move to a boundary in the ORIGINAL sequence; return new selected indices.

        Only the entries list order changes. Entry objects and all their fields survive.
        """
        entries = self.data["entries"]
        chosen = sorted(set(indices))
        if not 0 <= boundary <= len(entries):
            raise ValueError("Invalid insertion boundary")
        if any(i < 0 or i >= len(entries) or entries[i].get("is_category", False)
               for i in chosen):
            raise ValueError("Only songs can be moved")
        if not chosen:
            return []
        selected = set(chosen)
        moving = [entries[i] for i in chosen]
        remaining = [entry for i, entry in enumerate(entries) if i not in selected]
        destination = boundary - sum(i < boundary for i in chosen)
        entries[:] = remaining[:destination] + moving + remaining[destination:]
        return list(range(destination, destination + len(moving)))

    def insert_entry(self, index, *, song_path=None, category_name=None):
        if not 0 <= index <= len(self.data["entries"]):
            raise ValueError("Invalid insertion index")
        category = category_name is not None
        title = category_name.strip() if category else ntpath.splitext(ntpath.basename(song_path or ""))[0]
        if not title:
            raise ValueError("A song path or category name is required")
        entry = {
            "path": "" if category else str(song_path), "title": title,
            "sync_offset_ms": 0, "transpose_semitones": 0, "tempo_bpm": 0,
            "background_image_path": "", "background_dim": 45,
            "background_show_operator": True, "background_show_audience": True,
            "background_alignment": "center", "mixer_levels": [127] * 16,
            "chords_mode": "auto", "chords_track_index": -1,
            "is_category": category, "set_delay_seconds": 0, "set_flags": 0,
        }
        self.data["entries"].insert(index, entry)
        return entry

    def remove_entries(self, indices, *, categories=False):
        entries = self.data["entries"]
        chosen = set(indices)
        if any(i < 0 or i >= len(entries) or entries[i].get("is_category", False) != categories
               for i in chosen):
            raise ValueError("Invalid removal selection")
        entries[:] = [entry for i, entry in enumerate(entries) if i not in chosen]


def encode_json(value, depth=0):
    """Keep decimal JSON values exact, including unknown Cockpit fields."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Non-finite numbers cannot be saved as JSON")
        return str(value)
    indent = "  " * depth
    child_indent = indent + "  "
    if isinstance(value, dict):
        if not value:
            return "{}"
        parts = [child_indent + json.dumps(key, ensure_ascii=False) + ": " + encode_json(item, depth + 1)
                 for key, item in value.items()]
        return "{\n" + ",\n".join(parts) + "\n" + indent + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[\n" + ",\n".join(child_indent + encode_json(item, depth + 1) for item in value) + "\n" + indent + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)
