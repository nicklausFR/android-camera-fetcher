"""Compile the repository's simple Gettext .po files to .mo files."""
from __future__ import annotations
import ast
import struct
from pathlib import Path


def read_po(path: Path) -> dict[str, str]:
    messages, msgid, msgstr, field = {}, None, None, None
    for raw in path.read_text(encoding="utf-8").splitlines() + [""]:
        line = raw.strip()
        if not line:
            if msgid is not None: messages[msgid] = msgstr or ""
            msgid = msgstr = field = None; continue
        if line.startswith("msgid "): msgid, field = ast.literal_eval(line[6:]), "id"
        elif line.startswith("msgstr "): msgstr, field = ast.literal_eval(line[7:]), "str"
        elif line.startswith('"') and field == "id": msgid += ast.literal_eval(line)
        elif line.startswith('"') and field == "str": msgstr = (msgstr or "") + ast.literal_eval(line)
    return messages


def write_mo(messages: dict[str, str], path: Path) -> None:
    items = sorted((key.encode(), value.encode()) for key, value in messages.items())
    ids = b"\0".join(key for key, _ in items) + b"\0"; values = b"\0".join(value for _, value in items) + b"\0"
    count, offset = len(items), 28; id_table, value_table = offset, offset + count * 8; id_offset = value_table + count * 8; value_offset = id_offset + len(ids)
    id_entries=[]; value_entries=[]; pos=0
    for key,_ in items: id_entries.append((len(key),id_offset+pos)); pos += len(key)+1
    pos=0
    for _,value in items: value_entries.append((len(value),value_offset+pos)); pos += len(value)+1
    output=struct.pack("<7I",0x950412de,0,count,id_table,value_table,0,value_offset+len(values))
    output += b"".join(struct.pack("<2I",*entry) for entry in id_entries)+b"".join(struct.pack("<2I",*entry) for entry in value_entries)+ids+values
    path.write_bytes(output)


def extract_messages(project: Path) -> set[str]:
    """Collect literal calls to the project's gettext shorthand, _("...")."""
    messages = set()
    for source in project.glob("*.py"):
        if source.name == "i18n.py":
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "_":
                continue
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                messages.add(node.args[0].value)
    return messages


def write_pot(messages: set[str], path: Path) -> None:
    header = (
        'msgid ""\nmsgstr ""\n'
        '"Project-Id-Version: android-camera-fetcher\\n"\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
    )
    def quoted(value: str) -> str:
        return 'msgid ' + repr(value).replace("'", '"') + '\nmsgstr ""\n'
    path.write_text(header + "\n".join(quoted(message) for message in sorted(messages)), encoding="utf-8")


project = Path(__file__).parents[1]
write_pot(extract_messages(project), project / "locales" / "android-camera-fetcher.pot")
for po in project.glob("locales/*/LC_MESSAGES/*.po"):
    write_mo(read_po(po), po.with_suffix(".mo"))
