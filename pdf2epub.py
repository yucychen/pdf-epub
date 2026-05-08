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
          "({} chapters, {} images)".format(len(epub_chapters), image_counter))


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
    output = args.output or "{}.epub".format(title)
    convert(args.pdf, output, title, args.author, args.lang,
            cover_path=args.cover, no_cover=args.no_cover)


if __name__ == "__main__":
    main()
