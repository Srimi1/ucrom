#!/usr/bin/env python3
"""Create and inspect Android DTBO images (dtbo.img).

Implements the documented Android DT table format
(https://source.android.com/docs/core/architecture/dto/partitions):

  header (32 bytes, big-endian):
    magic 0xd7b7ab1e, total_size, header_size=32, dt_entry_size=32,
    dt_entry_count, dt_entries_offset=32, page_size, version=0
  entry (32 bytes each):
    dt_size, dt_offset, id, rev, custom[4]
  followed by the device tree overlay blobs.

  mkdtboimg.py create out.img [--page_size N] [--id ID] a.dtbo b.dtbo ...
  mkdtboimg.py dump dtbo.img
"""

import argparse
import struct
import sys

MAGIC = 0xD7B7AB1E
FDT_MAGIC = 0xD00DFEED
HDR = struct.Struct(">8I")
ENTRY = struct.Struct(">8I")


def create(out, files, page_size=4096, ids=None):
    blobs = []
    for f in files:
        data = open(f, "rb").read()
        if struct.unpack(">I", data[:4])[0] != FDT_MAGIC:
            raise SystemExit(f"{f}: not a flattened device tree")
        blobs.append(data)
    n = len(blobs)
    offset = HDR.size + n * ENTRY.size
    entries = []
    for i, b in enumerate(blobs):
        dt_id = ids[i] if ids else 0
        entries.append(ENTRY.pack(len(b), offset, dt_id, 0, 0, 0, 0, 0))
        offset += len(b)
    header = HDR.pack(MAGIC, offset, HDR.size, ENTRY.size, n, HDR.size, page_size, 0)
    with open(out, "wb") as f:
        f.write(header)
        for e in entries:
            f.write(e)
        for b in blobs:
            f.write(b)
    return offset


def dump(path):
    data = open(path, "rb").read()
    magic, total, hsize, esize, count, eoff, page, ver = HDR.unpack_from(data)
    if magic != MAGIC:
        raise SystemExit(f"{path}: bad magic {magic:#x}")
    info = {"total_size": total, "entry_count": count, "page_size": page, "version": ver,
            "size_ok": total == len(data), "entries": []}
    for i in range(count):
        size, off, dt_id, rev, *_ = ENTRY.unpack_from(data, eoff + i * esize)
        fdt_ok = struct.unpack_from(">I", data, off)[0] == FDT_MAGIC
        info["entries"].append({"size": size, "offset": off, "id": dt_id, "rev": rev, "fdt": fdt_ok})
    return info


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("out")
    c.add_argument("--page_size", type=int, default=4096)
    c.add_argument("dtbos", nargs="+")
    d = sub.add_parser("dump")
    d.add_argument("img")
    a = ap.parse_args()
    if a.cmd == "create":
        size = create(a.out, a.dtbos, a.page_size)
        print(f"{a.out}: {len(a.dtbos)} overlays, {size} bytes")
    else:
        import json
        print(json.dumps(dump(a.img), indent=2))


if __name__ == "__main__":
    sys.exit(main())
