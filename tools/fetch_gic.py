#!/usr/bin/env python3
"""
fetch_gic.py — Fetch and parse GIC register data from ARM documentation HTML.

This script attempts to download the ARM GIC Architecture Specification
(IHI0069) from the ARM developer website and parse its register tables into
the staging JSON format consumed by build_gic_index.py.

Data Acquisition Path (EB-0):
  EB-0-1  CMSIS SVD / IP-XACT check: No official ARM SVD for GIC was found in
          ARM-software/CMSIS_5 or community IP-XACT repos. The ARM System
          Register XML (SysReg_xml_A_profile) contains the Distributor CTLR
          register only (ext-gicd_ctlr.xml), not the full GIC register set.
          Conclusion: use HTML path.

  EB-0-2  HTML parseability check: The ARM developer documentation site
          (developer.arm.com/documentation/ihi0069/) is accessible as static
          HTML — register tables are present in <table> elements without
          requiring JavaScript. The site may be blocked in some environments.
          If this script cannot reach the site, the hand-curated gic/GIC.json
          file is the authoritative data source and this script is not needed.

Usage:
    python tools/fetch_gic.py [--dry-run] [--out DIR]

    --dry-run   Skip downloading; print what would be fetched.
    --out DIR   Write per-register staging JSON to DIR (default: /tmp/gic_staging).

This script is provided for transparency and future re-derivation.
The committed gic/GIC.json was produced by hand-curation from IHI0069H and
cross-referenced with ARM SysReg XML (SysReg_xml_A_profile-2023-03).

Requirements:
    Python 3.8+ stdlib only (urllib, html.parser, json, time, pathlib).

Rate limiting:
    Requests are spaced at least 2 seconds apart to respect ARM's CDN.

Exit codes:
    0  Success (or dry-run completed)
    1  Network error or parse failure
"""

import argparse
import html.parser
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ARM_GIC_BASE_URL = 'https://developer.arm.com/documentation/ihi0069/latest/'

# Known GIC register pages — path fragments under the spec base URL.
# These paths correspond to the IHI0069H (GIC Architecture Specification v3/v4).
GIC_REGISTER_PAGES = [
    # GICD registers
    ('GICD', 'GICD_CTLR',      'GICD_CTLR'),
    ('GICD', 'GICD_TYPER',     'GICD_TYPER'),
    ('GICD', 'GICD_IIDR',      'GICD_IIDR'),
    ('GICD', 'GICD_STATUSR',   'GICD_STATUSR'),
    ('GICD', 'GICD_IGROUPR',   'GICD_IGROUPR-n'),
    ('GICD', 'GICD_ISENABLER', 'GICD_ISENABLER-n'),
    ('GICD', 'GICD_ICENABLER', 'GICD_ICENABLER-n'),
    ('GICD', 'GICD_IPRIORITYR','GICD_IPRIORITYR-n'),
    ('GICD', 'GICD_ICFGR',     'GICD_ICFGR-n'),
    ('GICD', 'GICD_IGRPMODR',  'GICD_IGRPMODR-n'),
    ('GICD', 'GICD_IROUTER',   'GICD_IROUTER-n'),
    # GICR registers
    ('GICR', 'GICR_CTLR',     'GICR_CTLR'),
    ('GICR', 'GICR_IIDR',     'GICR_IIDR'),
    ('GICR', 'GICR_TYPER',    'GICR_TYPER'),
    ('GICR', 'GICR_STATUSR',  'GICR_STATUSR'),
    ('GICR', 'GICR_WAKER',    'GICR_WAKER'),
    ('GICR', 'GICR_PROPBASER','GICR_PROPBASER'),
    ('GICR', 'GICR_PENDBASER','GICR_PENDBASER'),
    # GITS registers
    ('GITS', 'GITS_CTLR',    'GITS_CTLR'),
    ('GITS', 'GITS_IIDR',    'GITS_IIDR'),
    ('GITS', 'GITS_TYPER',   'GITS_TYPER'),
    ('GITS', 'GITS_CBASER',  'GITS_CBASER'),
    ('GITS', 'GITS_CWRITER', 'GITS_CWRITER'),
    ('GITS', 'GITS_CREADR',  'GITS_CREADR'),
]

REQUEST_DELAY_SEC = 2.0
REQUEST_TIMEOUT_SEC = 15
USER_AGENT = 'AARCHMRS-GIC-Fetcher/1.0 (github.com/jonaschen/arm-mrs-2025-03-aarchmrs)'

# ---------------------------------------------------------------------------
# HTML parser for ARM register tables
# ---------------------------------------------------------------------------

class _RegisterTableParser(html.parser.HTMLParser):
    """
    Extract register field tables from an ARM architecture documentation page.

    ARM register pages contain <table> elements with rows structured as:
      <tr><td>BitRange</td><td>FieldName</td><td>AccessType</td><td>ResetValue</td><td>Description</td></tr>

    This parser captures those rows and builds a list of field dicts.
    """

    def __init__(self):
        super().__init__()
        self._in_table = False
        self._in_row   = False
        self._in_cell  = False
        self._cells    = []
        self._current  = ''
        self._rows     = []
        self.fields    = []
        self._depth    = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self._in_table = True
            self._rows = []
            self._depth += 1
        elif tag == 'tr' and self._in_table:
            self._in_row = True
            self._cells = []
        elif tag in ('td', 'th') and self._in_row:
            self._in_cell = True
            self._current = ''

    def handle_endtag(self, tag):
        if tag == 'table':
            self._depth -= 1
            if self._depth == 0:
                self._in_table = False
                self._extract_fields()
        elif tag == 'tr' and self._in_table:
            self._in_row = False
            if self._cells:
                self._rows.append(self._cells[:])
        elif tag in ('td', 'th') and self._in_row:
            self._in_cell = False
            self._cells.append(self._current.strip())

    def handle_data(self, data):
        if self._in_cell:
            self._current += data

    def _extract_fields(self):
        """Attempt to extract field rows from accumulated table rows."""
        for row in self._rows:
            if len(row) < 3:
                continue
            bits_str = row[0].strip()
            name     = row[1].strip() if len(row) > 1 else ''
            access   = row[2].strip() if len(row) > 2 else ''
            reset    = row[3].strip() if len(row) > 3 else ''
            brief    = row[4].strip() if len(row) > 4 else ''

            # Skip header rows
            if bits_str.lower() in ('bits', 'bit', 'field', 'name', 'range'):
                continue

            # Parse bit range: "31" or "31:28" or "[31:28]"
            bits_str = bits_str.strip('[]')
            bit_fields = _parse_bits(bits_str)
            if not bit_fields:
                continue

            if not name or name.lower() in ('reserved', 'res0', 'res1'):
                access = access or 'RES0'
                name   = name or 'RES0'

            self.fields.append({
                'name':   name,
                'bits':   bit_fields,
                'access': access or 'RO',
                'reset':  reset or '0',
                'brief':  brief or None,
            })


def _parse_bits(bits_str: str) -> list:
    """
    Parse a bit-range string like '31', '31:28', '31:0' into a bits list.
    Returns [] if the string cannot be parsed.
    """
    try:
        if ':' in bits_str:
            parts = bits_str.split(':')
            msb = int(parts[0].strip())
            lsb = int(parts[1].strip())
            if msb < lsb:
                msb, lsb = lsb, msb
            return [{'start': lsb, 'width': msb - lsb + 1}]
        else:
            bit = int(bits_str.strip())
            return [{'start': bit, 'width': 1}]
    except (ValueError, IndexError):
        return []


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _fetch_url(url: str) -> str:
    """Fetch a URL and return its text content. Raises urllib.error.URLError on failure."""
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
        return resp.read().decode('utf-8', errors='replace')


def fetch_register_page(block: str, reg_name: str, page_fragment: str,
                        dry_run: bool = False) -> dict | None:
    """
    Fetch one register page and return a staging dict, or None on failure.

    The returned dict has the structure expected by build_gic_index.py.
    """
    url = f'{ARM_GIC_BASE_URL}#{page_fragment}'
    if dry_run:
        print(f'  [dry-run] Would fetch: {url}')
        return None

    print(f'  Fetching {reg_name} from {url} ...', end=' ', flush=True)
    try:
        html_text = _fetch_url(url)
    except urllib.error.URLError as exc:
        print(f'FAILED ({exc})')
        return None

    parser = _RegisterTableParser()
    parser.feed(html_text)

    if not parser.fields:
        print(f'WARN (no fields parsed)')
        return None

    print(f'OK ({len(parser.fields)} fields)')
    return {
        'name':        reg_name,
        'block':       block,
        'offset':      None,  # not available from HTML; fill from spec
        'title':       reg_name,
        'brief':       None,
        'width':       32,
        'gic_versions': ['v3', 'v4'],
        'fieldsets': [
            {
                'id':          0,
                'condition':   None,
                'gic_versions': ['v3', 'v4'],
                'fields':      parser.fields,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Fetch GIC register data from ARM documentation HTML.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print what would be fetched without downloading.',
    )
    parser.add_argument(
        '--out', metavar='DIR', default='/tmp/gic_staging',
        help='Output directory for per-register staging JSON (default: /tmp/gic_staging).',
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    print('GIC Register Data Fetcher')
    print(f'Source: {ARM_GIC_BASE_URL}')
    print(f'Output: {out_dir}')
    print()

    ok_count   = 0
    fail_count = 0

    for block, reg_name, page_frag in GIC_REGISTER_PAGES:
        result = fetch_register_page(block, reg_name, page_frag, dry_run=args.dry_run)

        if result is not None:
            out_path = out_dir / f'{reg_name}.json'
            with open(out_path, 'w') as f:
                json.dump(result, f, indent=2)
            ok_count += 1
        elif not args.dry_run:
            fail_count += 1

        if not args.dry_run:
            time.sleep(REQUEST_DELAY_SEC)

    print()
    if args.dry_run:
        print(f'Dry-run complete. Would fetch {len(GIC_REGISTER_PAGES)} pages.')
        return 0

    print(f'Done. {ok_count} registers fetched, {fail_count} failed.')
    if fail_count:
        print('Note: For registers that failed, the hand-curated gic/GIC.json is the')
        print('authoritative source. Re-run this script with network access, or update')
        print('gic/GIC.json manually from IHI0069H.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
