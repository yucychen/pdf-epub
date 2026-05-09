"""GUI 包装,基于 tkinter(支持 image / text / auto 三模式)"""
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pdf2epub import convert


def run_convert(args, btn, status):
    try:
        status.set("转换中,请稍候...")
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
    root.geometry("620x500")

    pdf_var, out_var = tk.StringVar(), tk.StringVar()
    title_var, author_var = tk.StringVar(), tk.StringVar(value="Unknown")
    lang_var = tk.StringVar(value="zh")
    cover_var = tk.StringVar()
    mode_var = tk.StringVar(value="auto")
    ocr_var = tk.StringVar(value="off")
    ocr_lang_var = tk.StringVar(value="chi_sim+eng")
    status_var = tk.StringVar(value="选择 PDF 文件开始;扫描书选'图片模式'最稳")

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
            mode=mode_var.get(),
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

    # 模式选择
    ttk.Label(frm, text="转换模式:").grid(row=6, column=0, sticky="w", pady=4)
    mode_frame = ttk.Frame(frm)
    mode_frame.grid(row=6, column=1, sticky="w")
    ttk.Radiobutton(mode_frame, text="自动", variable=mode_var, value="auto").pack(side="left")
    ttk.Radiobutton(mode_frame, text="文字(电子书)", variable=mode_var, value="text").pack(side="left")
    ttk.Radiobutton(mode_frame, text="图片(扫描书)", variable=mode_var, value="image").pack(side="left")

    # OCR(仅 text 模式有用)
    ttk.Label(frm, text="OCR(仅文字模式):").grid(row=7, column=0, sticky="w", pady=4)
    ocr_frame = ttk.Frame(frm)
    ocr_frame.grid(row=7, column=1, sticky="w")
    ttk.Radiobutton(ocr_frame, text="关闭", variable=ocr_var, value="off").pack(side="left")
    ttk.Radiobutton(ocr_frame, text="自动", variable=ocr_var, value="auto").pack(side="left")
    ttk.Radiobutton(ocr_frame, text="强制", variable=ocr_var, value="force").pack(side="left")

    ttk.Label(frm, text="OCR 语言:").grid(row=8, column=0, sticky="w", pady=4)
    ttk.Combobox(frm, textvariable=ocr_lang_var, width=47,
                 values=["chi_sim+eng", "chi_tra+eng", "eng",
                         "jpn+eng", "kor+eng"]).grid(row=8, column=1, padx=4, sticky="w")

    start_btn = ttk.Button(frm, text="开始转换", command=start)
    start_btn.grid(row=9, column=0, columnspan=3, pady=12)
    ttk.Label(frm, textvariable=status_var, foreground="gray").grid(
        row=10, column=0, columnspan=3)

    ttk.Label(frm,
              text="提示:扫描书/漫画选「图片模式」效果最好,无需 Tesseract\n"
                   "「文字模式 + OCR 强制」可生成可搜索文本(需装 Tesseract)",
              foreground="#888", justify="left").grid(
        row=11, column=0, columnspan=3, pady=8, sticky="w")
    root.mainloop()


if __name__ == "__main__":
    main()
