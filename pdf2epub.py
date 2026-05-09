#!/usr/bin/env python3
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
    # 兜底:body 不能为空,否则 ebooklib 生成 nav 时 lxml 会报 "Document is empty"
    if not body and not imgs:
        body = "<p>&#160;</p>"
    # 注意:不要加 <?xml ?> 声明,ebooklib 内部用 html parser 解析,
    # 带 xml 声明 + 空 body 会触发 lxml.etree.ParserError
    return ('<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml">\n'
            '<head><meta charset="utf-8"/><title>{t}</title>\n'
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


def open_pdf(pdf_path):
    """更友好的 PDF 打开:文件不存在 / 0 字节 / 加密都给清晰错误"""
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError("PDF 不存在: {}".format(pdf_path))
    if os.path.getsize(pdf_path) == 0:
        raise ValueError("PDF 是空文件: {}".format(pdf_path))
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        raise RuntimeError(
            "无法打开 PDF: {}\n原因: {}\n"
            "可能是文件损坏或加密,请先用 PDF 工具检查".format(pdf_path, e)) from e
    if doc.is_encrypted:
        if not doc.authenticate(""):
            raise RuntimeError(
                "PDF 已加密: {}\n请先去除密码后再转换".format(pdf_path))
    if doc.page_count == 0:
        raise RuntimeError("PDF 没有任何页面: {}".format(pdf_path))
    return doc


def convert(pdf_path, epub_path, title, author, lang,
            cover_path=None, no_cover=False,
            ocr_mode="off", ocr_lang="chi_sim+eng", ocr_dpi=300):
    doc = open_pdf(pdf_path)
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
