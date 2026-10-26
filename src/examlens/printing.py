"""Send certificate pages straight to a Windows printer (no browser print window).

Uses .NET ``System.Drawing.Printing`` through PowerShell, which is part of every Windows
install, so no extra Python packages are needed. Each page image is drawn at its exact physical
size from the top-left corner of the sheet: the printer's unprintable "hard margin" is
subtracted so that positions are measured from the paper edge, exactly as in the template.
Nothing else is printed: no headers, footers, URLs or page numbers.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HUNDREDTHS_PER_MM = 100 / 25.4  # .NET paper sizes are in hundredths of an inch

_PS_PRELUDE = r"""
param([string]$JobFile)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Drawing
$job = Get-Content -Raw -Encoding UTF8 -LiteralPath $JobFile | ConvertFrom-Json
"""

_PS_LIST = (
    _PS_PRELUDE
    + r"""
$default = (New-Object System.Drawing.Printing.PrinterSettings).PrinterName
$out = @()
foreach ($name in [System.Drawing.Printing.PrinterSettings]::InstalledPrinters) {
  $s = New-Object System.Drawing.Printing.PrinterSettings
  $s.PrinterName = $name
  if (-not $s.IsValid) { continue }
  $papers = @($s.PaperSizes | ForEach-Object { @{ name = $_.PaperName; width = $_.Width; height = $_.Height; kind = "$($_.Kind)" } })
  $sources = @($s.PaperSources | ForEach-Object { @{ name = $_.SourceName; kind = "$($_.Kind)" } })
  $out += @{ name = $name; default = ($name -eq $default); papers = $papers; sources = $sources }
}
ConvertTo-Json -InputObject @($out) -Depth 5 -Compress
"""
)

_PS_PRINT = (
    _PS_PRELUDE
    + r"""
$doc = New-Object System.Drawing.Printing.PrintDocument
$doc.PrinterSettings.PrinterName = $job.printer
if (-not $doc.PrinterSettings.IsValid) { throw "Printer not found: $($job.printer)" }
$doc.DocumentName = $job.title
$doc.PrinterSettings.Copies = [int16]$job.copies
$doc.OriginAtMargins = $false
$page = $doc.DefaultPageSettings
$page.Landscape = $false
$page.Margins = New-Object System.Drawing.Printing.Margins(0, 0, 0, 0)
if ($job.paper) {
  $match = $doc.PrinterSettings.PaperSizes | Where-Object { $_.PaperName -eq $job.paper } | Select-Object -First 1
  if (-not $match) { throw "Paper size '$($job.paper)' is not available on $($job.printer)" }
  $page.PaperSize = $match
} else {
  $page.PaperSize = New-Object System.Drawing.Printing.PaperSize('Certificate', [int]$job.paper_w, [int]$job.paper_h)
}
if ($job.source) {
  $src = $doc.PrinterSettings.PaperSources | Where-Object { $_.SourceName -eq $job.source } | Select-Object -First 1
  if ($src) { $page.PaperSource = $src }
}
$state = @{ i = 0; hx = 0.0; hy = 0.0; w = 0.0; h = 0.0 }
$doc.add_PrintPage({
  param($sender, $e)
  $img = [System.Drawing.Image]::FromFile($job.pages[$state.i])
  try {
    $g = $e.Graphics
    if ($job.preview_dir) { $g.Clear([System.Drawing.Color]::White) }  # preview only: show paper as white
    $g.PageUnit = [System.Drawing.GraphicsUnit]::Millimeter
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    # On a real printer the drawing origin is the corner of the printable area, so shift back
    # by the hard margin to measure from the paper edge. Print preview already starts at the
    # paper edge: detect it by the drawable area being as wide as the paper.
    $clip = $g.VisibleClipBounds
    $paperW = $e.PageSettings.PaperSize.Width * 0.254
    if ($e.PageSettings.Landscape) { $paperW = $e.PageSettings.PaperSize.Height * 0.254 }
    if ($clip.Width -lt ($paperW - 0.5)) {
      $hx = $e.PageSettings.HardMarginX * 0.254
      $hy = $e.PageSettings.HardMarginY * 0.254
    } else { $hx = 0.0; $hy = 0.0 }
    $state.hx = $hx; $state.hy = $hy
    $state.w = $e.PageSettings.PaperSize.Width * 0.254; $state.h = $e.PageSettings.PaperSize.Height * 0.254
    $rect = New-Object System.Drawing.RectangleF([single](-$hx), [single](-$hy), [single]$job.width_mm, [single]$job.height_mm)
    $g.DrawImage($img, $rect)
  } finally { $img.Dispose() }
  $state.i++
  $e.HasMorePages = ($state.i -lt $job.pages.Count)
})
if ($job.preview_dir) {
  $ctl = New-Object System.Drawing.Printing.PreviewPrintController
  $ctl.UseAntiAlias = $true
  $doc.PrintController = $ctl
  $doc.Print()
  $n = 0
  foreach ($info in $ctl.GetPreviewPageInfo()) {
    $n++
    $info.Image.Save((Join-Path $job.preview_dir ("page_{0:000}.png" -f $n)), [System.Drawing.Imaging.ImageFormat]::Png)
  }
} else {
  $doc.PrintController = New-Object System.Drawing.Printing.StandardPrintController
  $doc.Print()
}
ConvertTo-Json -Compress -InputObject @{
  pages = $state.i; hard_margin_mm = @($state.hx, $state.hy); paper_mm = @($state.w, $state.h);
  paper = $page.PaperSize.PaperName; source = $page.PaperSource.SourceName
}
"""
)


class PrintError(Exception):
    """Printing failed; the message is safe to show to the user."""


@dataclass
class Printer:
    """An installed printer with its paper sizes (hundredths of an inch) and trays."""

    name: str
    default: bool = False
    papers: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)

    def manual_tray(self) -> str | None:
        """Name of the manual / bypass tray, the usual choice for certificate stock."""
        return next((s["name"] for s in self.sources if s.get("kind") == "Manual"), None)


@dataclass
class PrintResult:
    """What the printer received."""

    pages: int
    paper: str
    source: str
    hard_margin_mm: tuple[float, float]
    paper_mm: tuple[float, float]
    preview_pages: list[bytes] = field(default_factory=list)


def available() -> bool:
    """Direct printing works on Windows when PowerShell is present."""
    return os.name == "nt" and shutil.which("powershell") is not None


def _run(script: str, job: dict, timeout: int = 120) -> dict | list:
    work = Path(tempfile.mkdtemp(prefix="examlens_print_"))
    try:
        (work / "job.ps1").write_text(script, encoding="utf-8-sig")
        (work / "job.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(work / "job.ps1"),
                "-JobFile",
                str(work / "job.json"),
            ],
            capture_output=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0 or not out:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            first = next((line for line in err.splitlines() if line.strip()), "unknown error")
            raise PrintError(first.split(" : ", 1)[-1][:300])
        return json.loads(out.splitlines()[-1])
    except subprocess.TimeoutExpired as exc:
        raise PrintError("The printer did not respond in time.") from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


def list_printers() -> list[Printer]:
    """Installed printers, default first."""
    if not available():
        return []
    rows = _run(_PS_LIST, {}, timeout=60)
    printers = [
        Printer(r["name"], bool(r.get("default")), r.get("papers") or [], r.get("sources") or [])
        for r in rows
    ]
    return sorted(printers, key=lambda p: (not p.default, p.name.lower()))


def print_pages(
    images: list[bytes],
    printer: str,
    page_mm: tuple[float, float],
    paper: str | None = None,
    custom_paper_mm: tuple[float, float] | None = None,
    source: str | None = None,
    copies: int = 1,
    title: str = "Certificates",
    preview: bool = False,
) -> PrintResult:
    """Print PNG pages at ``page_mm`` from the paper's top-left corner.

    ``paper``: a paper-size name the printer lists, or ``None`` for a custom size of
    ``custom_paper_mm`` (defaults to ``page_mm``). ``preview``: render what the printer would
    receive into images instead of printing anything.
    """
    if not available():
        raise PrintError("Direct printing needs the app to run on Windows.")
    if not images:
        raise PrintError("Nothing to print.")
    work = Path(tempfile.mkdtemp(prefix="examlens_pages_"))
    try:
        paths = []
        for n, data in enumerate(images, start=1):
            path = work / f"page_{n:04d}.png"
            path.write_bytes(data)
            paths.append(str(path))
        preview_dir = work / "preview"
        if preview:
            preview_dir.mkdir()
        cw, ch = custom_paper_mm or page_mm
        job = {
            "printer": printer,
            "title": title,
            "copies": max(1, int(copies)),
            "paper": paper,
            "paper_w": round(cw * HUNDREDTHS_PER_MM),
            "paper_h": round(ch * HUNDREDTHS_PER_MM),
            "source": source,
            "pages": paths,
            "width_mm": page_mm[0],
            "height_mm": page_mm[1],
            "preview_dir": str(preview_dir) if preview else None,
        }
        out = _run(_PS_PRINT, job, timeout=60 + 5 * len(images))
        pages = sorted(preview_dir.glob("page_*.png")) if preview else []
        return PrintResult(
            pages=int(out.get("pages", 0)),
            paper=str(out.get("paper", "")),
            source=str(out.get("source", "")),
            hard_margin_mm=tuple(out.get("hard_margin_mm", (0.0, 0.0))),
            paper_mm=tuple(out.get("paper_mm", (0.0, 0.0))),
            preview_pages=[p.read_bytes() for p in pages],
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)
