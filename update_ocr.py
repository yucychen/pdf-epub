# -*- coding: utf-8 -*-
"""为 pdf-epub 项目增加 OCR 支持"""
import os

FILES = {}

# ---------- requirements.txt ----------
FILES["requirements.txt"] = """\
PyMuPDF>=1.24.0
EbookLib>=0.18
beautifulsoup4>=4.12.0
Pillow>=10.0.0
pyinstaller>=6.6.0
pytesseract>=0.3.10
"""

# ---------- pdf2epub.py ----------
FILES["pdf2epub.py"] = r'''#!/usr/bin/env python3
"""PDF -> EPUB 转换工具(支持 OCR)
用法:
    python pdf2epub.py input.pdf -o output.epub -t "书名" -a "作者"
    python pdf2epub.py scan.pdf --ocr force --ocr-lang chi_sim+eng
"""
import argparse
import io
import os
import re
import shutil
import sys
import uuid
from html import escape

import fitz  # PyMuPDF
from ebooklib import epub

# ---------------- OCR 支持 ----------------
try:
    import pytesseract
    from PIL import Image
    _HAS_PYTESS = True
except Exception:
    _HAS_PYTESS = False


def _find_tesseract():
    """自动定位 tesseract 可执行文件(Windows 常见路径)"""
    if shutil.which("tesseract"):
        return "tesseract"
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def ocr_page(page, lang="chi_sim+eng", dpi=300):
    """对一页做 OCR,返回识别出的文本"""
    if not _HAS_PYTESS:
        raise RuntimeError("pytesseract 未安装,请 pip install pytesseract")
    tess = _find_tesseract()
    if not tess:
        raise RuntimeError(
            "未找到 Tesseract。请安装:\n"
            "  Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "  macOS:   brew install tesseract tesseract-lang\n"
            "  Linux:   sudo apt install tesseract-ocr tesseract-ocr-chi-sim")
    pytesseract.pytesseract.tesseract_cmd = tess

    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img, lang=lang)


# ---------------- 文本处理 ----------------
def clean_text(text):
    text = re.sub(r"-\n(\w)", r"\1", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def text_to_html(title, text, image_tags):
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    body = "\n".join("<p>{}</p>".format(escape(p)) for p in paragraphs)
    imgs = "\n".join(image_tags)
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml">\n'
            '<head><title>{t}</title>\n'
            '<link rel="stylesheet" type="text/css" href="style/main.css"/></head>\n'
            '<body>\n<h1>{t}</h1>\n{i}\n{b}\n</body></html>'
            ).format(t=escape(title), i=imgs, b=body)


def extract_chapters(doc):
    toc = doc.get_toc()
    chapters = []
    if toc:
        top = [t for t in toc if t[0] == 1] or toc
        for i, (_lvl, title, page) in enumerate(top):
            start = max(0, page - 1)
            end = (top[i + 1][2] - 1) if i + 1 < len(top) else doc.page_count
            chapters.append((title.strip() or "Chapter {}".format(i + 1), start, end))
    else:
        chunk = 20
        for i in range(0, doc.page_count, chunk):
            chapters.append(("Pages {}-{}".format(i + 1, min(i + chunk, doc.page_count)),
                             i, min(i + chunk, doc.page_count)))
    return chapters


def render_cover(doc, dpi=150):
    page = doc.load_page(0)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def get_page_text(page, ocr_mode, ocr_lang, ocr_dpi):
    """根据 ocr_mode 返回页面文本
    ocr_mode: off / auto / force
    """
    raw = page.get_text("text") if ocr_mode != "force" else ""
    if ocr_mode == "off":
        return clean_text(raw)
    # auto: 文字少于阈值才 OCR
    if ocr_mode == "auto" and len(raw.strip()) >= 30:
        return clean_text(raw)
    # 走 OCR
    try:
        ocr_txt = ocr_page(page, lang=ocr_lang, dpi=ocr_dpi)
        return clean_text(ocr_txt)
    except Exception as e:
        print("WARN: OCR failed on page {}: {}".format(page.number + 1, e))
        return clean_text(raw)


def convert(pdf_path, epub_path, title, author, lang,
            cover_path=None, no_cover=False,
            ocr_mode="off", ocr_lang="chi_sim+eng", ocr_dpi=300):
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
            book.set_cover("cover." + ext, cover_bytes)
        except Exception as e:
            print("WARN: cover generation failed, skipped:", e)

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
    total = doc.page_count
    done = 0

    for idx, (ch_title, start, end) in enumerate(chapters, 1):
        text_parts, image_tags = [], []
        for pno in range(start, end):
            page = doc.load_page(pno)
            text_parts.append(get_page_text(page, ocr_mode, ocr_lang, ocr_dpi))
            done += 1
            if ocr_mode != "off":
                print("  page {}/{}".format(done, total), flush=True)
            # 图片提取(OCR force 模式跳过,避免重复)
            if ocr_mode != "force":
                for img in page.get_images(full=True):
                    xref = img[0]
                    try:
                        base = doc.extract_image(xref)
                    except Exception:
                        continue
                    image_counter += 1
                    ext = base["ext"]
                    img_name = "images/img_{}.{}".format(image_counter, ext)
                    media = "image/" + ("jpeg" if ext == "jpg" else ext)
                    book.add_item(epub.EpubItem(
                        uid="img_{}".format(image_counter), file_name=img_name,
                        media_type=media, content=base["image"]))
                    image_tags.append('<img src="{}" alt=""/>'.format(img_name))

        chapter_text = "\n\n".join(p for p in text_parts if p)
        c = epub.EpubHtml(title=ch_title,
                          file_name="chap_{:03d}.xhtml".format(idx), lang=lang)
        c.content = text_to_html(ch_title, chapter_text, image_tags)
        c.add_item(css)
        book.add_item(c)
        epub_chapters.append(c)

    book.toc = tuple(epub_chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + epub_chapters

    epub.write_epub(epub_path, book)
    print("Done:", epub_path,
          "({} chapters, {} images, ocr={})".format(
              len(epub_chapters), image_counter, ocr_mode))


def main():
    p = argparse.ArgumentParser(description="Convert PDF to EPUB (with OCR)")
    p.add_argument("pdf")
    p.add_argument("-o", "--output")
    p.add_argument("-t", "--title")
    p.add_argument("-a", "--author", default="Unknown")
    p.add_argument("-l", "--lang", default="zh")
    p.add_argument("-c", "--cover", help="Custom cover image (png/jpg)")
    p.add_argument("--no-cover", action="store_true")
    p.add_argument("--ocr", choices=["off", "auto", "force"], default="off",
                   help="OCR mode: off(默认) / auto(无文字时才OCR) / force(全部OCR)")
    p.add_argument("--ocr-lang", default="chi_sim+eng",
                   help="Tesseract 语言包,默认 chi_sim+eng;英文 eng;繁体 chi_tra")
    p.add_argument("--ocr-dpi", type=int, default=300,
                   help="OCR 渲染 DPI,默认 300(更清晰但更慢)")
    args = p.parse_args()
    title = args.title or os.path.splitext(os.path.basename(args.pdf))[0]
    output = args.output or "{}.epub".format(title)
    convert(args.pdf, output, title, args.author, args.lang,
            cover_path=args.cover, no_cover=args.no_cover,
            ocr_mode=args.ocr, ocr_lang=args.ocr_lang, ocr_dpi=args.ocr_dpi)


if __name__ == "__main__":
    main()
'''

# ---------- pdf2epub_gui.py ----------
FILES["pdf2epub_gui.py"] = r'''"""GUI 包装,基于 tkinter(支持 OCR)"""
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pdf2epub import convert


def run_convert(args, btn, status):
    try:
        status.set("转换中,请稍候...(OCR 较慢,请耐心)")
        btn.config(state="disabled")
        convert(**args)
        status.set("完成")
        messagebox.showinfo("完成", "已生成:\n" + args["epub_path"])
    except Exception as e:
        status.set("失败")
        messagebox.showerror("错误", str(e))
    finally:
        btn.config(state="normal")


def main():
    root = tk.Tk()
    root.title("PDF -> EPUB 转换器")
    root.geometry("600x440")

    pdf_var, out_var = tk.StringVar(), tk.StringVar()
    title_var, author_var = tk.StringVar(), tk.StringVar(value="Unknown")
    lang_var = tk.StringVar(value="zh")
    cover_var = tk.StringVar()
    ocr_var = tk.StringVar(value="off")
    ocr_lang_var = tk.StringVar(value="chi_sim+eng")
    status_var = tk.StringVar(value="选择 PDF 文件开始(扫描版请勾选 OCR)")

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
        args = dict(
            pdf_path=pdf_var.get(), epub_path=out_var.get(),
            title=title_var.get() or "Untitled",
            author=author_var.get() or "Unknown",
            lang=lang_var.get() or "zh",
            cover_path=cover_var.get() or None,
            ocr_mode=ocr_var.get(),
            ocr_lang=ocr_lang_var.get() or "chi_sim+eng",
        )
        threading.Thread(target=run_convert, daemon=True,
                         args=(args, start_btn, status_var)).start()

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

    # OCR 选项
    ttk.Label(frm, text="OCR 模式:").grid(row=6, column=0, sticky="w", pady=4)
    ocr_frame = ttk.Frame(frm)
    ocr_frame.grid(row=6, column=1, sticky="w")
    ttk.Radiobutton(ocr_frame, text="关闭", variable=ocr_var, value="off").pack(side="left")
    ttk.Radiobutton(ocr_frame, text="自动", variable=ocr_var, value="auto").pack(side="left")
    ttk.Radiobutton(ocr_frame, text="强制", variable=ocr_var, value="force").pack(side="left")

    ttk.Label(frm, text="OCR 语言:").grid(row=7, column=0, sticky="w", pady=4)
    lang_combo = ttk.Combobox(frm, textvariable=ocr_lang_var, width=47,
                              values=["chi_sim+eng", "chi_tra+eng", "eng",
                                      "jpn+eng", "kor+eng"])
    lang_combo.grid(row=7, column=1, padx=4, sticky="w")

    start_btn = ttk.Button(frm, text="开始转换", command=start)
    start_btn.grid(row=8, column=0, columnspan=3, pady=12)
    ttk.Label(frm, textvariable=status_var, foreground="gray").grid(
        row=9, column=0, columnspan=3)

    ttk.Label(frm, text="提示:扫描版 PDF 选'强制'或'自动';需先安装 Tesseract",
              foreground="#888").grid(row=10, column=0, columnspan=3, pady=4)
    root.mainloop()


if __name__ == "__main__":
    main()
'''

# ---------- .github/workflows/build.yml(CI 自动装 Tesseract) ----------
FILES[".github/workflows/build.yml"] = """\
name: Build & Release

on:
  push:
    tags: ['v*']
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
          python-version: '3.11'

      - name: Install Tesseract (Linux)
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra tesseract-ocr-jpn tesseract-ocr-kor
      - name: Install Tesseract (macOS)
        if: runner.os == 'macOS'
        run: brew install tesseract tesseract-lang
      - name: Install Tesseract (Windows)
        if: runner.os == 'Windows'
        run: choco install -y tesseract

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Generate icons
        env:
          FORCE_ICNS: '1'
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
    if: startsWith(github.ref, 'refs/tags/v')
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
"""


def main():
    for path, content in FILES.items():
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        print("  ~", path)
    print("\nOCR 支持已加入!下一步:")
    print("  git add .")
    print('  git commit -m "feat: add OCR support"')
    print("  git push origin main")
    print("  git tag v1.1.0 && git push origin v1.1.0")


if __name__ == "__main__":
    main()