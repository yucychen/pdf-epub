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
        messagebox.showinfo("完成", "已生成:\n" + epub_path)
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
