"""Compiles gettext .po catalogs to .mo files – the part of GNU msgfmt this project needs, standard library only.

Supports message contexts, plural forms, multi-line strings and C escapes; leaves out fuzzy, obsolete and
untranslated entries like msgfmt does. The output has no hash table, which the .mo format allows.

    python3 tools/msgfmt.py -o OUT.mo IN.po
"""

import ast
import struct
import sys
from pathlib import Path

MAGIC = 0x950412DE
KEYWORDS = ("msgctxt", "msgid", "msgid_plural", "msgstr")


class PoError(ValueError):
    pass


def _string(token: str, lineno: int) -> str:
    if not (len(token) >= 2 and token.startswith('"') and token.endswith('"')):
        raise PoError(f"line {lineno}: expected a quoted string, got {token!r}")
    try:
        value = ast.literal_eval(token)
    except (ValueError, SyntaxError) as e:
        raise PoError(f"line {lineno}: invalid string {token!r}") from e
    if not isinstance(value, str):
        raise PoError(f"line {lineno}: invalid string {token!r}")
    return value


def _has_msgstr(entry: dict) -> bool:
    return any(k.startswith("msgstr") for k in entry)


def _add(catalog: dict[bytes, bytes], entry: dict) -> None:
    if "msgid" not in entry:
        return
    key = entry["msgid"]
    if "msgctxt" in entry:
        key = entry["msgctxt"] + "\x04" + key
    if "msgid_plural" in entry:
        forms = [entry[k] for k in sorted((k for k in entry if k.startswith("msgstr[")), key=lambda k: int(k[7:-1]))]
        if not any(forms):
            return
        key += "\0" + entry["msgid_plural"]
        value = "\0".join(forms)
    else:
        value = entry.get("msgstr", "")
        if not value:
            return
    catalog[key.encode("utf-8")] = value.encode("utf-8")


def parse(text: str) -> dict[bytes, bytes]:
    """Return {key: translation} as stored in a .mo file (context and plural forms joined like msgfmt)."""
    catalog: dict[bytes, bytes] = {}
    entry: dict[str, str] = {}
    flags: set[str] = set()
    field = None

    def finish() -> None:
        nonlocal entry, flags, field
        if "fuzzy" not in flags:
            _add(catalog, entry)
        entry, flags, field = {}, set(), None

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#~"):  # blank line or obsolete entry
            continue
        if line.startswith("#"):
            if _has_msgstr(entry):
                finish()
            if line.startswith("#,"):
                flags.update(f.strip() for f in line[2:].split(","))
            continue
        if line.startswith('"'):
            if field is None:
                raise PoError(f"line {lineno}: string without keyword")
            entry[field] += _string(line, lineno)
            continue
        keyword, _, rest = line.partition(" ")
        if keyword not in KEYWORDS and not (keyword.startswith("msgstr[") and keyword.endswith("]")
                                            and keyword[7:-1].isdigit()):
            raise PoError(f"line {lineno}: unknown keyword {keyword!r}")
        if keyword in ("msgctxt", "msgid") and _has_msgstr(entry):
            finish()
        field = keyword
        entry[field] = _string(rest.strip(), lineno)
    finish()

    header = catalog.get(b"", b"").decode("utf-8").lower()
    if "charset=" in header and "charset=utf-8" not in header:
        raise PoError("only UTF-8 catalogs are supported")
    return catalog


def mo_bytes(catalog: dict[bytes, bytes]) -> bytes:
    keys = sorted(catalog)
    ids = strs = b""
    offsets = []
    for k in keys:
        offsets.append((len(ids), len(k), len(strs), len(catalog[k])))
        ids += k + b"\0"
        strs += catalog[k] + b"\0"
    n = len(keys)
    keystart = 7 * 4 + 16 * n
    valuestart = keystart + len(ids)
    key_table, value_table = [], []
    for id_off, id_len, str_off, str_len in offsets:
        key_table += [id_len, keystart + id_off]
        value_table += [str_len, valuestart + str_off]
    header = struct.pack("<7I", MAGIC, 0, n, 7 * 4, 7 * 4 + 8 * n, 0, keystart)
    return header + struct.pack(f"<{2 * n}I", *key_table) + struct.pack(f"<{2 * n}I", *value_table) + ids + strs


def compile_file(po: Path, mo: Path) -> None:
    try:
        catalog = parse(po.read_text(encoding="utf-8"))
    except PoError as e:
        raise PoError(f"{po}: {e}") from e
    mo.parent.mkdir(parents=True, exist_ok=True)
    mo.write_bytes(mo_bytes(catalog))


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] != "-o":
        print("usage: msgfmt.py -o OUT.mo IN.po", file=sys.stderr)
        return 2
    try:
        compile_file(Path(argv[2]), Path(argv[1]))
    except (OSError, PoError) as e:
        print(f"msgfmt.py: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
