#!/usr/bin/env python3
"""PDF -> EPUB 转换工具 (v1.1.3 - 多进程加速)"""
import argparse
import io
import os
import re
import shutil
import sys
import uuid
from html import escape
from concurrent.futures import ProcessPoolExecutor, as_completed

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
        raise RuntimeError("未找到 Tesseract,请先安装")
    pytesseract.pytesseract.tesseract_cmd = tess
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
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
        body = "<p>&#160;</p>"
    return ('<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml">\n'
            '<head><meta charset="utf-8"/><title>{t}</title>\n'
            '<link rel="stylesheet" type="text/css" href="style/main.css"/></head>\n'
            '<body>\n<h1>{t}</h1>\n{i}\n{b}\n</body></html>'
            ).format(t=escape(title), i=imgs, b=body)


def extract_chapters(doc, max_pages_per_chapter=20):
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


def render_cover(doc, dpi=120):
    pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0),
                                       alpha=False)
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
    n = min(sample, doc.page_count)
    text_pages = sum(1 for i in range(n)
                     if len(doc.load_page(i).get_text("text").strip()) >= 50)
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


# -------- 多进程渲染 worker(必须是顶级函数才能被 pickle) --------
def _render_one(args):
    """子进程:打开 PDF,渲染指定页,返回 (页号, jpeg字节)"""
    pdf_path, page_no, dpi, quality = args
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(page_no)
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        # ★ PyMuPDF 直出 JPEG,无需 Pillow,快 2-3 倍
        try:
            data = pix.tobytes("jpeg", jpg_quality=quality)
        except (TypeError, ValueError):
            # 老版本 PyMuPDF 不支持 jpeg,fallback 到 PNG
            data = pix.tobytes("png")
            return page_no, data, "png", "image/png"
        return page_no, data, "jpg", "image/jpeg"
    finally:
        doc.close()


def render_pages_parallel(pdf_path, page_indices, dpi, quality, workers, total):
    """并行渲染一组页面,按页号顺序返回结果"""
    tasks = [(pdf_path, p, dpi, quality) for p in page_indices]
    results = {}
    done = 0
    if workers <= 1:
        for t in tasks:
            page_no, data, ext, media = _render_one(t)
            results[page_no] = (data, ext, media)
            done += 1
            if done % 10 == 0 or done == len(tasks):
                print("  rendered {}/{}".format(done, total), flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for fut in as_completed(ex.submit(_render_one, t) for t in tasks):
                page_no, data, ext, media = fut.result()
                results[page_no] = (data, ext, media)
                done += 1
                if done % 10 == 0 or done == len(tasks):
                    print("  rendered {}/{}".format(done, total), flush=True)
    return [(p, *results[p]) for p in page_indices]


def convert(pdf_path, epub_path, title, author, lang,
            cover_path=None, no_cover=False,
            mode="auto",
            ocr_mode="off", ocr_lang="chi_sim+eng", ocr_dpi=300,
            image_dpi=120, image_quality=80, workers=None):
    doc = open_pdf(pdf_path)
    actual_mode = mode if mode != "auto" else detect_mode(doc)
    if workers is None:
        workers = max(1, (os.cpu_count() or 2) - 1)
    print("Mode: {} (requested: {}), pages: {}, workers: {}".format(
        actual_mode, mode, doc.page_count, workers if actual_mode == "image" else 1))

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
        uid="style_main", file_name="style/main.css", media_type="text/css",
        content=("body{margin:0;padding:0;font-family:serif;line-height:1.6;}"
                 "h1{font-size:1.4em;margin:1em;}"
                 "p{margin:0.6em 1em;text-indent:2em;}"
                 ".page{text-align:center;margin:0;padding:0;}"
                 "img{max-width:100%;height:auto;display:block;margin:0 auto;}"))
    book.add_item(css)

    chapters = extract_chapters(doc)
    epub_chapters = []
    image_counter = 0
    total = doc.page_count

    # ★ image 模式:先并行渲染所有页,再组装章节(最大化并行度)
    rendered = {}
    if actual_mode == "image":
        all_pages = list(range(total))
        for page_no, data, ext, media in render_pages_parallel(
                pdf_path, all_pages, image_dpi, image_quality, workers, total):
            rendered[page_no] = (data, ext, media)

    done_text = 0
    for idx, (ch_title, start, end) in enumerate(chapters, 1):
        text_parts, image_tags = [], []

        for pno in range(start, end):
            if actual_mode == "image":
                data, ext, media = rendered[pno]
                image_counter += 1
                img_name = "images/page_{:04d}.{}".format(pno + 1, ext)
                book.add_item(epub.EpubItem(
                    uid="page_{}".format(pno + 1), file_name=img_name,
                    media_type=media, content=data))
                image_tags.append(
                    '<div class="page"><img src="{}" alt="page {}"/></div>'.format(
                        img_name, pno + 1))
            else:
                page = doc.load_page(pno)
                text_parts.append(get_page_text(page, ocr_mode, ocr_lang, ocr_dpi))
                done_text += 1
                if ocr_mode != "off" and (done_text % 5 == 0 or done_text == total):
                    print("  ocr {}/{}".format(done_text, total), flush=True)
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

    print("Writing EPUB ...", flush=True)
    epub.write_epub(epub_path, book)
    print("Done:", epub_path,
          "({} chapters, {} images, mode={})".format(
              len(epub_chapters), image_counter, actual_mode))


def main():
    p = argparse.ArgumentParser(description="Convert PDF to EPUB")
    p.add_argument("pdf")
    p.add_argument("-o", "--output")
    p.add_argument("-t", "--title")
    p.add_argument("-a", "--author", default="Unknown")
    p.add_argument("-l", "--lang", default="zh")
    p.add_argument("-c", "--cover")
    p.add_argument("--no-cover", action="store_true")
    p.add_argument("--mode", choices=["auto", "text", "image"], default="auto")
    p.add_argument("--image-dpi", type=int, default=120,
                   help="image 模式 DPI(默认 120,提高更清晰但更慢/更大)")
    p.add_argument("--image-quality", type=int, default=80,
                   help="JPEG 质量 1-95,默认 80")
    p.add_argument("--workers", type=int, default=None,
                   help="并行进程数,默认 CPU核心数-1。设 1 关闭并行")
    p.add_argument("--ocr", choices=["off", "auto", "force"], default="off")
    p.add_argument("--ocr-lang", default="chi_sim+eng")
    p.add_argument("--ocr-dpi", type=int, default=300)
    args = p.parse_args()
    title = args.title or os.path.splitext(os.path.basename(args.pdf))[0]
    output = args.output or "{}.epub".format(title)
    convert(args.pdf, output, title, args.author, args.lang,
            cover_path=args.cover, no_cover=args.no_cover, mode=args.mode,
            ocr_mode=args.ocr, ocr_lang=args.ocr_lang, ocr_dpi=args.ocr_dpi,
            image_dpi=args.image_dpi, image_quality=args.image_quality,
            workers=args.workers)


if __name__ == "__main__":
    main()
