# 一键生成 pdf-epub 项目所有文件 (PowerShell 版)
$ErrorActionPreference = "Stop"

# 强制 UTF-8 输出,避免中文乱码
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Write-File($path, $content) {
    $dir = Split-Path -Parent $path
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [System.IO.File]::WriteAllText((Resolve-Path -LiteralPath . ).Path + "\" + $path, $content, $utf8NoBom)
    Write-Host "  + $path"
}

Write-Host "Generating project files..." -ForegroundColor Cyan

# ---------- requirements.txt ----------
Write-File "requirements.txt" @'
PyMuPDF>=1.24.0
EbookLib>=0.18
beautifulsoup4>=4.12.0
Pillow>=10.0.0
pyinstaller>=6.6.0
'@

# ---------- .gitignore ----------
Write-File ".gitignore" @'
__pycache__/
*.pyc
.venv/
venv/
build/
dist/
*.egg-info/
*.epub
*.pdf
.DS_Store
assets/icon.ico
assets/icon.icns
assets/icon.png
'@

# ---------- pdf2epub.py ----------
Write-File "pdf2epub.py" @'
#!/usr/bin/env python3
"""PDF -> EPUB 转换工具
用法: python pdf2epub.py input.pdf -o output.epub -t "书名" -a "作者"
"""
import argparse
import os
import re
import uuid
from html import escape

import fitz  # PyMuPDF
from ebooklib import epub


def clean_text(text: str) -> str:
    text = re.sub(r"-\n(\w)", r"\1", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def text_to_html(title, text, image_tags):
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    body = "\n".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    imgs = "\n".join(image_tags)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{escape(title)}</title>
<link rel="stylesheet" type="text/css" href="style/main.css"/></head>
<body>
<h1>{escape(title)}</h1>
{imgs}
{body}
</body></html>"""


def extract_chapters(doc):
    toc = doc.get_toc()
    chapters = []
    if toc:
        top = [t for t in toc if t[0] == 1] or toc
        for i, (_lvl, title, page) in enumerate(top):
            start = max(0, page - 1)
            end = (top[i + 1][2] - 1) if i + 1 < len(top) else doc.page_count
            chapters.append((title.strip() or f"Chapter {i+1}", start, end))
    else:
        chunk = 20
        for i in range(0, doc.page_count, chunk):
            chapters.append((f"Pages {i+1}-{min(i+chunk, doc.page_count)}",
                             i, min(i + chunk, doc.page_count)))
    return chapters


def render_cover(doc, dpi: int = 150) -> bytes:
    page = doc.load_page(0)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def convert(pdf_path, epub_path, title, author, lang,
            cover_path=None, no_cover=False):
    doc = fitz.open(pdf_path)
    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(title)
    book.set_language(lang)
    book.add_author(author)

    if not no_cover:
        try:
            if cover_path and os.path.isfile(cover_path):
                with open(cover_path, "rb") as f:
                    cover_bytes = f.read()
                ext = os.path.splitext(cover_path)[1].lstrip(".").lower() or "png"
            else:
                cover_bytes = render_cover(doc)
                ext = "png"
            book.set_cover(f"cover.{ext}", cover_bytes)
        except Exception as e:
            print(f"WARN: cover generation failed, skipped: {e}")

    css = epub.EpubItem(
        uid="style_main", file_name="style/main.css",
        media_type="text/css",
        content=("body{font-family:serif;line-height:1.6;margin:1em;}"
                 "h1{font-size:1.4em;margin:1em 0;}"
                 "p{margin:0.6em 0;text-indent:2em;}"
                 "img{max-width:100%;height:auto;display:block;margin:1em auto;}")
    )
    book.add_item(css)

    chapters = extract_chapters(doc)
    epub_chapters = []
    image_counter = 0

    for idx, (ch_title, start, end) in enumerate(chapters, 1):
        text_parts, image_tags = [], []
        for pno in range(start, end):
            page = doc.load_page(pno)
            text_parts.append(clean_text(page.get_text("text")))
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    base = doc.extract_image(xref)
                except Exception:
                    continue
                image_counter += 1
                ext = base["ext"]
                img_name = f"images/img_{image_counter}.{ext}"
                media = f"image/{'jpeg' if ext == 'jpg' else ext}"
                book.add_item(epub.EpubItem(
                    uid=f"img_{image_counter}", file_name=img_name,
                    media_type=media, content=base["image"]))
                image_tags.append(f'<img src="{img_name}" alt=""/>')

        chapter_text = "\n\n".join(p for p in text_parts if p)
        c = epub.EpubHtml(title=ch_title,
                          file_name=f"chap_{idx:03d}.xhtml", lang=lang)
        c.content = text_to_html(ch_title, chapter_text, image_tags)
        c.add_item(css)
        book.add_item(c)
        epub_chapters.append(c)

    book.toc = tuple(epub_chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *epub_chapters]

    epub.write_epub(epub_path, book)
    print(f"Done: {epub_path}  ({len(epub_chapters)} chapters, {image_counter} images)")


def main():
    p = argparse.ArgumentParser(description="Convert PDF to EPUB")
    p.add_argument("pdf")
    p.add_argument("-o", "--output")
    p.add_argument("-t", "--title")
    p.add_argument("-a", "--author", default="Unknown")
    p.add_argument("-l", "--lang", default="zh")
    p.add_argument("-c", "--cover", help="Custom cover image (png/jpg)")
    p.add_argument("--no-cover", action="store_true")
    args = p.parse_args()
    title = args.title or os.path.splitext(os.path.basename(args.pdf))[0]
    output = args.output or f"{title}.epub"
    convert(args.pdf, output, title, args.author, args.lang,
            cover_path=args.cover, no_cover=args.no_cover)


if __name__ == "__main__":
    main()
'@

# ---------- pdf2epub_gui.py ----------
Write-File "pdf2epub_gui.py" @'
"""GUI 包装,基于 tkinter"""
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pdf2epub import convert


def run_convert(pdf_path, epub_path, title, author, lang, cover, btn, status):
    try:
        status.set("转换中,请稍候...")
        btn.config(state="disabled")
        convert(pdf_path, epub_path, title, author, lang, cover_path=cover or None)
        status.set("完成")
        messagebox.showinfo("完成", f"已生成:\n{epub_path}")
    except Exception as e:
        status.set("失败")
        messagebox.showerror("错误", str(e))
    finally:
        btn.config(state="normal")


def main():
    root = tk.Tk()
    root.title("PDF -> EPUB 转换器")
    root.geometry("560x320")

    pdf_var, out_var = tk.StringVar(), tk.StringVar()
    title_var, author_var = tk.StringVar(), tk.StringVar(value="Unknown")
    lang_var = tk.StringVar(value="zh")
    cover_var = tk.StringVar()
    status_var = tk.StringVar(value="选择 PDF 文件开始(封面默认取首页)")

    def pick_pdf():
        p = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if p:
            pdf_var.set(p)
            if not out_var.get():
                out_var.set(p.rsplit(".", 1)[0] + ".epub")
            if not title_var.get():
                title_var.set(os.path.splitext(os.path.basename(p))[0])

    def pick_out():
        p = filedialog.asksaveasfilename(defaultextension=".epub",
                                         filetypes=[("EPUB", "*.epub")])
        if p:
            out_var.set(p)

    def pick_cover():
        p = filedialog.askopenfilename(filetypes=[("Image", "*.png *.jpg *.jpeg")])
        if p:
            cover_var.set(p)

    def start():
        if not pdf_var.get() or not out_var.get():
            messagebox.showwarning("提示", "请选择输入 PDF 和输出 EPUB 路径")
            return
        threading.Thread(target=run_convert, daemon=True,
                         args=(pdf_var.get(), out_var.get(),
                               title_var.get() or "Untitled",
                               author_var.get() or "Unknown",
                               lang_var.get() or "zh",
                               cover_var.get(),
                               start_btn, status_var)).start()

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)

    def row(label, var, browse, r):
        ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=var, width=50).grid(row=r, column=1, padx=4)
        if browse:
            ttk.Button(frm, text="...", width=3, command=browse).grid(row=r, column=2)

    row("输入 PDF:", pdf_var, pick_pdf, 0)
    row("输出 EPUB:", out_var, pick_out, 1)
    row("书名:", title_var, None, 2)
    row("作者:", author_var, None, 3)
    row("语言:", lang_var, None, 4)
    row("封面(可选):", cover_var, pick_cover, 5)

    start_btn = ttk.Button(frm, text="开始转换", command=start)
    start_btn.grid(row=6, column=0, columnspan=3, pady=12)
    ttk.Label(frm, textvariable=status_var, foreground="gray").grid(
        row=7, column=0, columnspan=3)
    root.mainloop()


if __name__ == "__main__":
    main()
'@

# ---------- make_icon.py ----------
Write-File "make_icon.py" @'
"""用 Pillow 生成应用图标 (assets/icon.ico / icon.icns / icon.png)"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = "assets"
SIZES = [16, 24, 32, 48, 64, 128, 256, 512]


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(1, size // 16)
    radius = size // 5
    d.rounded_rectangle([pad, pad, size - pad, size - pad],
                        radius=radius, fill=(43, 108, 176, 255))
    text = "P>E"
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size * 0.42))
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1] - size * 0.03),
           text, font=font, fill=(255, 255, 255, 255))
    return img


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    images = [draw_icon(s) for s in SIZES]
    images[-1].save(os.path.join(OUT_DIR, "icon.png"))
    images[-2].save(os.path.join(OUT_DIR, "icon.ico"),
                    sizes=[(s, s) for s in SIZES if s <= 256])
    if sys.platform == "darwin" or os.environ.get("FORCE_ICNS"):
        try:
            images[-1].save(os.path.join(OUT_DIR, "icon.icns"))
        except Exception as e:
            print(f"icns generation failed (non-fatal): {e}")
    print("Icons generated in", OUT_DIR)


if __name__ == "__main__":
    main()
'@

# ---------- pdf2epub.spec ----------
Write-File "pdf2epub.spec" @'
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: 同时构建 CLI 与 GUI,带应用图标"""
import os
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

if sys.platform.startswith("win"):
    _icon = os.path.join("assets", "icon.ico")
elif sys.platform == "darwin":
    _icon = os.path.join("assets", "icon.icns")
else:
    _icon = os.path.join("assets", "icon.png")
icon_arg = _icon if os.path.exists(_icon) else None

hidden, datas, binaries = [], [], []
for pkg in ("fitz", "ebooklib"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hidden += h

cli_a = Analysis(["pdf2epub.py"], pathex=[], binaries=binaries, datas=datas,
                 hiddenimports=hidden, hookspath=[], runtime_hooks=[],
                 excludes=[], cipher=block_cipher, noarchive=False)
cli_pyz = PYZ(cli_a.pure, cli_a.zipped_data, cipher=block_cipher)
cli_exe = EXE(cli_pyz, cli_a.scripts, [], exclude_binaries=True,
              name="pdf2epub", console=True, icon=icon_arg)

gui_a = Analysis(["pdf2epub_gui.py"], pathex=[], binaries=binaries, datas=datas,
                 hiddenimports=hidden + ["pdf2epub"], hookspath=[],
                 runtime_hooks=[], excludes=[], cipher=block_cipher,
                 noarchive=False)
gui_pyz = PYZ(gui_a.pure, gui_a.zipped_data, cipher=block_cipher)
gui_exe = EXE(gui_pyz, gui_a.scripts, [], exclude_binaries=True,
              name="pdf2epub-gui", console=False, icon=icon_arg)

coll = COLLECT(
    cli_exe, cli_a.binaries, cli_a.zipfiles, cli_a.datas,
    gui_exe, gui_a.binaries, gui_a.zipfiles, gui_a.datas,
    strip=False, upx=True, upx_exclude=[], name="pdf2epub",
)
'@

# ---------- build.bat ----------
Write-File "build.bat" @'
@echo off
setlocal
python -m pip install -r requirements.txt || exit /b 1
python make_icon.py || exit /b 1
pyinstaller pdf2epub.spec --clean --noconfirm || exit /b 1
echo.
echo ====== Done ======
echo Output: dist\pdf2epub\
echo   - pdf2epub.exe       (CLI)
echo   - pdf2epub-gui.exe   (GUI, double-click)
'@

# ---------- build.sh ----------
Write-File "build.sh" @'
#!/usr/bin/env bash
set -e
python3 -m pip install -r requirements.txt
FORCE_ICNS=1 python3 make_icon.py
pyinstaller pdf2epub.spec --clean --noconfirm
echo
echo "====== Done ======"
echo "Output: dist/pdf2epub/"
echo "  - pdf2epub        (CLI)"
echo "  - pdf2epub-gui    (GUI)"
'@

# ---------- .github/workflows/build.yml ----------
Write-File ".github/workflows/build.yml" @'
name: Build & Release

on:
  push:
    tags: ["v*"]
  workflow_dispatch:

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, macos-latest, ubuntu-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Generate icons
        env:
          FORCE_ICNS: "1"
        run: python make_icon.py
      - name: Build with PyInstaller
        run: pyinstaller pdf2epub.spec --clean --noconfirm
      - name: Package archive
        shell: bash
        run: |
          cd dist
          if [ "$RUNNER_OS" = "Windows" ]; then
            7z a -tzip pdf2epub-${{ runner.os }}.zip pdf2epub
          else
            tar -czf pdf2epub-${{ runner.os }}.tar.gz pdf2epub
          fi
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: pdf2epub-${{ runner.os }}
          path: |
            dist/pdf2epub-${{ runner.os }}.zip
            dist/pdf2epub-${{ runner.os }}.tar.gz
          if-no-files-found: ignore

  release:
    needs: build
    if: startsWith(github.ref, "refs/tags/v")
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          path: artifacts
      - run: find artifacts -type f
      - uses: softprops/action-gh-release@v2
        with:
          name: ${{ github.ref_name }}
          generate_release_notes: true
          files: |
            artifacts/**/pdf2epub-*.zip
            artifacts/**/pdf2epub-*.tar.gz
'@

# ---------- README.md ----------
Write-File "README.md" @'
# pdf-epub

一个简单好用的 **PDF → EPUB** 转换工具,基于 PyMuPDF + EbookLib。

- ✅ 命令行 (`pdf2epub`) + 图形界面 (`pdf2epub-gui`)
- ✅ 自动按 PDF 大纲生成章节与目录
- ✅ 提取并嵌入图片
- ✅ 自动从首页生成封面(可自定义)
- ✅ 一键 PyInstaller 打包,Win/Mac/Linux 通吃
- ✅ 打 tag 自动出三平台 Release

## 快速开始

```bash
pip install -r requirements.txt
python pdf2epub.py book.pdf -o book.epub -t "书名" -a "作者"
# 或 GUI
python pdf2epub_gui.py
```

## 打包成可执行文件

Windows: `build.bat`
macOS / Linux: `chmod +x build.sh && ./build.sh`

产物在 `dist/pdf2epub/`,包含 CLI 与 GUI 两个可执行文件。

## 自动发布

```bash
git tag v1.0.0
git push origin v1.0.0
```

几分钟后 Releases 页会出现三平台压缩包。
'@

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "All files generated successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  git add ."
Write-Host "  git commit -m 'feat: PDF->EPUB tool full version'"
Write-Host "  git push origin main"
Write-Host "  git tag v1.0.0"
Write-Host "  git push origin v1.0.0"
Write-Host ""