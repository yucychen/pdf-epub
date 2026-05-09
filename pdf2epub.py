#!/usr/bin/env python3
"""PDF -> EPUB 转换工具
支持三种模式:
  text  : 提取文字层(适合电子书原生 PDF),可选 OCR
  image : 每页渲染成图直接嵌入(适合扫描书/漫画,无需 OCR,可读性最高)
  auto  : 自动判断(默认)— 扫描页走 image,文字页走 text

用法示例:
  python pdf2epub.py book.pdf -o book.epub               # auto 模式
  python pdf2epub.py scan.pdf --mode image               # 强制图片模式
  python pdf2epub.py scan.pdf --mode text --ocr force    # 全本 OCR
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

# ---------------- OCR(可选) ----------------
try:
    import pytesseract
    from PIL import Image
    _HAS_PYTESS = True
except Exception:
    _HAS_PYTESS = False


def _find_tesseract():
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
    if not body and not imgs:
        body = "<p>&#160;</p>"  # 兜底,避免 lxml "Document is empty"
    return ('<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml">\n'
            '<head><meta charset="utf-8"/><title>{t}</title>\n'
            '<link rel="stylesheet" type="text/css" href="style/main.css"/></head>\n'
            '<body>\n<h1>{t}</h1>\n{i}\n{b}\n</body></html>'
            ).format(t=escape(title), i=imgs, b=body)


def extract_chapters(doc, max_pages_per_chapter=20):
    """根据 PDF 大纲分章;无大纲时按固定页数分块"""
    toc = doc.get_toc()
    chapters = []
    if toc:
        top = [t for t in toc if t[0] == 1] or toc
        for i, (_lvl, title, page) in enumerate(top):
            start = max(0, page - 1)
            end = (top[i + 1][2] - 1) if i + 1 < len(top) else doc.page_count
            chapters.append((title.strip() or "Chapter {}".format(i + 1), start, end))
    else:
        for i in range(0, doc.page_count, max_pages_per_chapter):
            chapters.append(("Pages {}-{}".format(
                i + 1, min(i + max_pages_per_chapter, doc.page_count)),
                i, min(i + max_pages_per_chapter, doc.page_count)))
    return chapters


def render_cover(doc, dpi=150):
    page = doc.load_page(0)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")


def open_pdf(pdf_path):
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError("PDF 不存在: {}".format(pdf_path))
    if os.path.getsize(pdf_path) == 0:
        raise ValueError("PDF 是空文件: {}".format(pdf_path))
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        raise RuntimeError("无法打开 PDF: {}\n原因: {}".format(pdf_path, e)) from e
    if doc.is_encrypted and not doc.authenticate(""):
        raise RuntimeError("PDF 已加密: {}\n请先去除密码".format(pdf_path))
    if doc.page_count == 0:
        raise RuntimeError("PDF 没有任何页面: {}".format(pdf_path))
    return doc


def detect_mode(doc, sample=10):
    """auto 模式自动检测:扫描书 -> image,文字书 -> text"""
    n = min(sample, doc.page_count)
    text_pages = 0
    for i in range(n):
        if len(doc.load_page(i).get_text("text").strip()) >= 50:
            text_pages += 1
    return "text" if text_pages >= n / 2 else "image"


def get_page_text(page, ocr_mode, ocr_lang, ocr_dpi):
    raw = page.get_text("text") if ocr_mode != "force" else ""
    if ocr_mode == "off":
        return clean_text(raw)
    if ocr_mode == "auto" and len(raw.strip()) >= 30:
        return clean_text(raw)
    try:
        return clean_text(ocr_page(page, lang=ocr_lang, dpi=ocr_dpi))
    except Exception as e:
        print("WARN: OCR failed on page {}: {}".format(page.number + 1, e))
        return clean_text(raw)


def render_page_image(page, dpi=150, fmt="jpeg", quality=80):
    """把一页渲染成图片字节流"""
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    if fmt == "png":
        return pix.tobytes("png"), "png", "image/png"
    # jpeg(默认,体积小)
    img = Image.open(io.BytesIO(pix.tobytes("png"))) if _HAS_PYTESS else None
    if img is None:
        # 没装 Pillow 也能 fallback 成 png
        return pix.tobytes("png"), "png", "image/png"
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), "jpg", "image/jpeg"


def convert(pdf_path, epub_path, title, author, lang,
            cover_path=None, no_cover=False,
            mode="auto",
            ocr_mode="off", ocr_lang="chi_sim+eng", ocr_dpi=300,
            image_dpi=150, image_quality=80):
    doc = open_pdf(pdf_path)

    # 决定最终模式
    actual_mode = mode if mode != "auto" else detect_mode(doc)
    print("Mode: {} (requested: {}), pages: {}".format(
        actual_mode, mode, doc.page_count))

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(title)
    book.set_language(lang)
    book.add_author(author)

    # 封面
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

    # CSS
    css = epub.EpubItem(
        uid="style_main", file_name="style/main.css",
        media_type="text/css",
        content=("body{margin:0;padding:0;font-family:serif;line-height:1.6;}"
                 "h1{font-size:1.4em;margin:1em;}"
                 "p{margin:0.6em 1em;text-indent:2em;}"
                 ".page{text-align:center;margin:0;padding:0;}"
                 "img{max-width:100%;height:auto;display:block;margin:0 auto;}")
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
            done += 1

            if actual_mode == "image":
                # ★ 图片模式:每页渲染一张图,直接放进章节
                try:
                    data, ext, media = render_page_image(
                        page, dpi=image_dpi, quality=image_quality)
                except Exception as e:
                    print("WARN: render page {} failed: {}".format(pno + 1, e))
                    continue
                image_counter += 1
                img_name = "images/page_{:04d}.{}".format(pno + 1, ext)
                book.add_item(epub.EpubItem(
                    uid="page_{}".format(pno + 1), file_name=img_name,
                    media_type=media, content=data))
                image_tags.append(
                    '<div class="page"><img src="{}" alt="page {}"/></div>'.format(
                        img_name, pno + 1))
                if done % 10 == 0 or done == total:
                    print("  page {}/{}".format(done, total), flush=True)
            else:
                # text 模式:提取文字(可选 OCR)+ 嵌入页面里的图片
                text_parts.append(get_page_text(page, ocr_mode, ocr_lang, ocr_dpi))
                if ocr_mode != "off":
                    print("  page {}/{}".format(done, total), flush=True)
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
          "({} chapters, {} images, mode={})".format(
              len(epub_chapters), image_counter, actual_mode))


def main():
    p = argparse.ArgumentParser(
        description="Convert PDF to EPUB (text / image / auto)")
    p.add_argument("pdf")
    p.add_argument("-o", "--output")
    p.add_argument("-t", "--title")
    p.add_argument("-a", "--author", default="Unknown")
    p.add_argument("-l", "--lang", default="zh")
    p.add_argument("-c", "--cover", help="Custom cover image (png/jpg)")
    p.add_argument("--no-cover", action="store_true")
    p.add_argument("--mode", choices=["auto", "text", "image"], default="auto",
                   help="转换模式:auto(默认)/ text(文字层) / image(每页渲染成图,适合扫描书)")
    p.add_argument("--image-dpi", type=int, default=150,
                   help="image 模式渲染 DPI,默认 150。提高更清晰但文件更大")
    p.add_argument("--image-quality", type=int, default=80,
                   help="image 模式 JPEG 质量 (1-95),默认 80")
    p.add_argument("--ocr", choices=["off", "auto", "force"], default="off",
                   help="text 模式下的 OCR:off/auto/force")
    p.add_argument("--ocr-lang", default="chi_sim+eng")
    p.add_argument("--ocr-dpi", type=int, default=300)
    args = p.parse_args()
    title = args.title or os.path.splitext(os.path.basename(args.pdf))[0]
    output = args.output or "{}.epub".format(title)
    convert(args.pdf, output, title, args.author, args.lang,
            cover_path=args.cover, no_cover=args.no_cover,
            mode=args.mode,
            ocr_mode=args.ocr, ocr_lang=args.ocr_lang, ocr_dpi=args.ocr_dpi,
            image_dpi=args.image_dpi, image_quality=args.image_quality)


if __name__ == "__main__":
    main()
