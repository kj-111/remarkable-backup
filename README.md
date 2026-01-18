# remarkable-backup

Offline backup and export tool for reMarkable tablets. **Supports .rm v6 format.**

## Features

- **Backup** - Sync tablet data via rsync over SSH (read-only, no cloud)
- **PDF Export** - Overlay annotations on original PDFs
- **SVG Export** - Extract annotations as standalone SVG files
- **Incremental** - Only exports changed documents
- **Folder Structure** - Preserves your reMarkable folder hierarchy

## Requirements

- reMarkable tablet (tested with reMarkable 2)
- SSH access to tablet (USB or WiFi)
- Python 3.9+

## Installation

```bash
git clone https://github.com/kj-111/remarkable-backup.git
cd remarkable-backup

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

ssh-copy-id root@10.11.99.1
```

## Usage

Connect tablet via USB, then:

```bash
./bin/rm-backup
```

This will:
1. Sync data to `xochitl/`
2. Export SVGs to `output/svg-tool/`
3. Export annotated PDFs to `output/pdf-tool/`

### Options

```bash
./bin/rm-backup --no-svg    # Backup only, skip exports
```

### Manual export

```bash
python -m src.pdf_export           # PDF export
python -m src.pdf_export --force   # Force re-export all
python -m src.export               # SVG export
```

## Output

```
output/
├── svg-tool/           # SVG annotations
│   └── my-notebook/
│       ├── page-001.svg
│       └── page-002.svg
└── pdf-tool/           # Annotated PDFs
    └── my-book.pdf
```

## Why v6?

reMarkable firmware 3.x uses .rm file format version 6. Many existing tools only support older formats (v3-v5). This tool parses v6 natively.

## License

MIT
