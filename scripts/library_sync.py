"""Strateji ve coin listelerini repoya aktar / repodan geri yükle.

Kullanım:
    python scripts/library_sync.py export                # library/ altına yaz
    python scripts/library_sync.py export --prune        # artık olmayan dosyaları sil
    python scripts/library_sync.py import                # yalnızca önizleme
    python scripts/library_sync.py import --apply        # veritabanına uygula

Veritabanının tamamı yedeklenmez; yalnızca kullanıcı stratejileri ve coin
listeleri JSON olarak saklanır. Dosyalar Git'e eklenebilir.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import library_sync  # noqa: E402


def _export(args: argparse.Namespace) -> int:
    summary = library_sync.export_library(
        args.directory,
        include_archived=not args.no_archived,
        include_builtin_lists=args.include_builtin_lists,
        prune=args.prune,
    )
    print(f"Dizin: {summary['directory']}")
    print(f"  {summary['strategies']} strateji, {summary['coinlists']} coin listesi yazıldı")
    if summary["removed"]:
        print(f"  {summary['removed']} eski dosya silindi")
    print("\nGit'e eklemek için:")
    print(f"  git add {Path(args.directory).as_posix()}")
    return 0


def _import(args: argparse.Namespace) -> int:
    report = library_sync.import_library(args.directory, apply=args.apply)
    lines = library_sync.summarize(report)
    if lines:
        print("\n".join(lines))
    else:
        print("Aktarılacak dosya bulunamadı.")
    counts = {"create": 0, "update": 0, "skip": 0}
    for key in ("strategies", "coinlists"):
        for entry in report.get(key) or []:
            counts[entry["action"]] = counts.get(entry["action"], 0) + 1
    print(
        f"\n{counts.get('create', 0)} eklenecek, {counts.get('update', 0)} güncellenecek, "
        f"{counts.get('skip', 0)} değişmedi, {len(report.get('errors') or [])} hata"
    )
    if not args.apply:
        print("Önizleme modu. Uygulamak için: --apply")
    return 0 if not report.get("errors") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    exp = sub.add_parser("export", help="Veritabanından dosyalara yaz")
    exp.add_argument(
        "--dir",
        default=str(ROOT / "library"),
        help="Kütüphane dizini (varsayılan: library/)",
    )
    exp.add_argument("--no-archived", action="store_true", help="Arşiv stratejileri atla")
    exp.add_argument(
        "--include-builtin-lists",
        action="store_true",
        help="Hazır coin listelerini de yaz",
    )
    exp.add_argument("--prune", action="store_true", help="Artık olmayan JSON dosyalarını sil")
    exp.set_defaults(func=_export)

    imp = sub.add_parser("import", help="Dosyalardan veritabanına yükle")
    imp.add_argument(
        "--dir",
        default=str(ROOT / "library"),
        help="Kütüphane dizini (varsayılan: library/)",
    )
    imp.add_argument("--apply", action="store_true", help="Değişiklikleri gerçekten uygula")
    imp.set_defaults(func=_import)

    args = parser.parse_args()
    args.directory = args.dir
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
