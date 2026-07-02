#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Backup Viewer by Danial Afshari
=====================
یک برنامه گرافیکی ساده (بدون نیاز به نصب پکیج اضافه، فقط پایتون استاندارد)
برای مرور فایل بکاپ/Export گرفته‌شده از Claude.ai

فایل مورد نیاز: همان ZIP که از Settings > Privacy > Export data دریافت کردی
(شامل conversations.json ، memories.json ، users.json و پوشه projects/)

اجرا:
    python3 claude_backup_viewer.py

سپس از منوی File گزینه "Open Export (zip or folder)" را بزن و فایل
zip یا پوشه‌ی استخراج‌شده را انتخاب کن.
دانیال افشاری
"""

import json
import os
import re
import sys
import html
import zipfile
import tempfile
import shutil
import webbrowser
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Tkinter's text widgets do NOT do Unicode bidi-reordering or Arabic/Persian
# glyph shaping on their own (this is true on every OS, not just Linux).
# These two small libraries fix that for display inside the app:
#   pip install arabic-reshaper python-bidi
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    RTL_SUPPORT = True
except ImportError:
    RTL_SUPPORT = False


def shape_rtl(text):
    """Reshape + reorder Persian/Arabic text so it displays correctly inside
    Tkinter widgets. Falls back to the raw text if the libraries aren't
    installed (in which case Persian text will look reversed/disjointed)."""
    if not RTL_SUPPORT or not text:
        return text
    shaped_lines = []
    for line in text.split("\n"):
        try:
            shaped_lines.append(get_display(arabic_reshaper.reshape(line)))
        except Exception:
            shaped_lines.append(line)
    return "\n".join(shaped_lines)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

class ExportData:
    def __init__(self):
        self.users = []
        self.memories = []
        self.conversations = []
        self.projects = []
        self.root_dir = None

    def load(self, path):
        """path can be a .zip file or an already-extracted folder."""
        if os.path.isdir(path):
            self.root_dir = path
        elif zipfile.is_zipfile(path):
            tmpdir = tempfile.mkdtemp(prefix="claude_export_")
            with zipfile.ZipFile(path) as zf:
                zf.extractall(tmpdir)
            self.root_dir = tmpdir
        else:
            raise ValueError("The selected path is neither a valid folder nor a zip file.")

        self.users = self._load_json("users.json", default=[])
        self.memories = self._load_json("memories.json", default=[])
        self.conversations = self._load_json("conversations.json", default=[])

        self.projects = []
        proj_dir = os.path.join(self.root_dir, "projects")
        if os.path.isdir(proj_dir):
            for fname in sorted(os.listdir(proj_dir)):
                if fname.endswith(".json"):
                    try:
                        with open(os.path.join(proj_dir, fname), encoding="utf-8") as f:
                            self.projects.append(json.load(f))
                    except Exception:
                        pass

        # sort conversations by last update, newest first
        self.conversations.sort(key=lambda c: c.get("updated_at", ""), reverse=True)

    def _load_json(self, filename, default):
        fpath = os.path.join(self.root_dir, filename)
        if not os.path.isfile(fpath):
            return default
        try:
            with open(fpath, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default


def fmt_date(iso_str):
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str[:16]


def build_conversation_html(conv):
    """Build a standalone HTML page for a conversation. Browsers handle
    Persian/Arabic bidi + shaping perfectly on their own, so this is the
    most reliable way to read long / heavily-wrapped conversations."""
    esc = html.escape
    code_fence_re = re.compile(r"```(\w*)\n?(.*?)```", re.DOTALL)

    def esc_nl(t):
        return esc(t or "").replace("\n", "<br>")

    def render_body(text):
        """Turn plain text into HTML, rendering fenced ```code``` blocks as
        separate, individually-copyable code panes (like Claude.ai)."""
        out = []
        pos = 0
        for m in code_fence_re.finditer(text):
            before = text[pos:m.start()]
            if before:
                out.append(f"<div>{esc_nl(before)}</div>")
            lang = esc(m.group(1) or "code")
            code = esc(m.group(2).rstrip("\n"))
            out.append(
                "<div class='codewrap'>"
                f"<div class='codebar'><span>{lang}</span>"
                "<button class='copybtn' onclick=\"copyCode(this)\">Copy</button></div>"
                f"<pre class='codeblock'><code>{code}</code></pre>"
                "</div>"
            )
            pos = m.end()
        remainder = text[pos:]
        if remainder:
            out.append(f"<div>{esc_nl(remainder)}</div>")
        return "".join(out)

    parts = [
        "<!DOCTYPE html><html dir='rtl' lang='fa'><head><meta charset='utf-8'>",
        f"<title>{esc(conv.get('name', ''))}</title>",
        "<style>",
        "body{font-family:Tahoma,'Vazirmatn','Segoe UI',sans-serif;",
        "max-width:900px;margin:30px auto;padding:0 16px;line-height:2;background:#fafafa;color:#222}",
        "h1{font-size:22px}",
        ".msg{border-radius:10px;padding:14px 18px;margin:14px 0;white-space:normal}",
        ".user{background:#eaf1ff}",
        ".assistant{background:#fff3ea}",
        ".thinking{color:#888;font-style:italic;font-size:0.9em;margin-top:6px}",
        ".tool{color:#0a7d3b;font-size:0.9em;margin-top:6px}",
        ".role{font-weight:bold;margin-bottom:8px}",
        ".user .role{color:#0b5fff}",
        ".assistant .role{color:#c2410c}",
        ".meta{color:#777;font-size:0.85em;margin-bottom:20px}",
        ".codewrap{direction:ltr;text-align:left;margin:10px 0;border-radius:8px;overflow:hidden;",
        "background:#1e1e1e}",
        ".codebar{display:flex;justify-content:space-between;align-items:center;",
        "background:#2d2d2d;color:#9da5b4;font:12px Consolas,monospace;padding:4px 10px}",
        ".copybtn{background:#3c3c3c;color:#fff;border:none;border-radius:4px;",
        "font:11px 'Segoe UI',sans-serif;padding:3px 10px;cursor:pointer}",
        ".copybtn:hover{background:#4a4a4a}",
        ".codeblock{margin:0;padding:12px 14px;overflow-x:auto;color:#d4d4d4;",
        "font:13px Consolas,monospace;white-space:pre}",
        "</style>",
        "<script>",
        "function copyCode(btn){",
        "  var code = btn.closest('.codewrap').querySelector('code').innerText;",
        "  function done(){",
        "    var old = btn.innerText; btn.innerText = 'Copied!';",
        "    setTimeout(function(){ btn.innerText = old; }, 1200);",
        "  }",
        "  if (navigator.clipboard && window.isSecureContext) {",
        "    navigator.clipboard.writeText(code).then(done).catch(function(){ fallbackCopy(code, done); });",
        "  } else {",
        "    fallbackCopy(code, done);",
        "  }",
        "}",
        "function fallbackCopy(text, done){",
        "  var ta = document.createElement('textarea');",
        "  ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';",
        "  document.body.appendChild(ta); ta.select();",
        "  try { document.execCommand('copy'); } catch(e) {}",
        "  document.body.removeChild(ta); done();",
        "}",
        "</script>",
        "</head><body>",
        f"<h1>{esc(conv.get('name', ''))}</h1>",
        f"<div class='meta'>Created: {esc(fmt_date(conv.get('created_at', '')))}"
        f" | Updated: {esc(fmt_date(conv.get('updated_at', '')))}</div>",
    ]

    for msg in conv.get("chat_messages", []):
        is_user = msg.get("sender") == "human"
        role_class = "user" if is_user else "assistant"
        role_label = "You" if is_user else "Claude"
        parts.append(f"<div class='msg {role_class}'><div class='role'>{role_label}</div>")

        blocks = msg.get("content") or []
        if not blocks and msg.get("text"):
            parts.append(render_body(msg["text"]))
        for block in blocks:
            btype = block.get("type")
            if btype == "text" and block.get("text"):
                parts.append(render_body(block["text"]))
            elif btype == "thinking" and block.get("thinking"):
                parts.append(f"<div class='thinking'>[thinking] {esc_nl(block['thinking'])}</div>")
            elif btype == "tool_use":
                parts.append(f"<div class='tool'>[used tool: {esc(block.get('name',''))}]</div>")
            elif btype == "tool_result":
                parts.append("<div class='tool'>[tool result received]</div>")

        for f in (msg.get("files") or []) + (msg.get("attachments") or []):
            fname = f.get("file_name") or f.get("name") or "attachment"
            parts.append(f"<div class='tool'>📎 {esc(fname)}</div>")

        parts.append("</div>")

    parts.append("</body></html>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class ViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Claude Backup Viewer")
        self.root.geometry("1150x720")

        self.data = ExportData()
        self.filtered_conversations = []

        self._build_menu()
        self._build_layout()

    # ---------------- UI construction ----------------

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Open Export (zip or folder)...", command=self.open_export)
        filemenu.add_separator()
        filemenu.add_command(label="Open Conversation in Browser (best Persian rendering)",
                              command=self.open_in_browser)
        filemenu.add_command(label="Export Conversation as .txt",
                              command=self.export_current_conversation)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=filemenu)
        self.root.config(menu=menubar)

    def _build_layout(self):
        # Top: search bar
        top = ttk.Frame(self.root)
        top.pack(side="top", fill="x", padx=6, pady=6)

        ttk.Label(top, text="Search:").pack(side="left", padx=(4, 0))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.apply_filter())
        search_entry = ttk.Entry(top, textvariable=self.search_var, justify="right")
        search_entry.pack(side="left", fill="x", expand=True, padx=6)

        self.status_var = tk.StringVar(value="No export loaded — use File > Open Export.")
        ttk.Label(top, textvariable=self.status_var).pack(side="left", padx=10)
        ttk.Button(top, text="Open in Browser", command=self.open_in_browser).pack(side="right", padx=6)
        if not RTL_SUPPORT:
            ttk.Label(top, text="⚠ For correct Persian text run: pip install arabic-reshaper python-bidi",
                      foreground="#b00020").pack(side="right", padx=10)

        # Main split: left = tabs (conversations/projects/memory), right = content viewer
        main = ttk.PanedWindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        left = ttk.Frame(main, width=380)
        main.add(left, weight=1)

        right = ttk.Frame(main)
        main.add(right, weight=3)

        # --- left: notebook with Conversations / Projects / Memory ---
        self.left_nb = ttk.Notebook(left)
        self.left_nb.pack(fill="both", expand=True)

        # Conversations tab
        conv_tab = ttk.Frame(self.left_nb)
        self.left_nb.add(conv_tab, text="Conversations")

        columns = ("date",)
        self.conv_list = ttk.Treeview(conv_tab, columns=columns, show="tree headings", selectmode="browse")
        self.conv_list.heading("#0", text="Title")
        self.conv_list.heading("date", text="Date")
        self.conv_list.column("#0", width=250)
        self.conv_list.column("date", width=110, anchor="center")
        self.conv_list.pack(fill="both", expand=True, side="left")
        conv_scroll = ttk.Scrollbar(conv_tab, orient="vertical", command=self.conv_list.yview)
        conv_scroll.pack(side="right", fill="y")
        self.conv_list.configure(yscrollcommand=conv_scroll.set)
        self.conv_list.bind("<<TreeviewSelect>>", self.on_select_conversation)

        # Projects tab
        proj_tab = ttk.Frame(self.left_nb)
        self.left_nb.add(proj_tab, text="Projects")
        self.proj_list = tk.Listbox(proj_tab, exportselection=False)
        self.proj_list.pack(fill="both", expand=True, side="left")
        proj_scroll = ttk.Scrollbar(proj_tab, orient="vertical", command=self.proj_list.yview)
        proj_scroll.pack(side="right", fill="y")
        self.proj_list.configure(yscrollcommand=proj_scroll.set)
        self.proj_list.bind("<<ListboxSelect>>", self.on_select_project)

        # Memory tab
        mem_tab = ttk.Frame(self.left_nb)
        self.left_nb.add(mem_tab, text="Memory")
        ttk.Button(mem_tab, text="Show Memory", command=self.show_memory).pack(pady=10)

        # --- right: content display ---
        self.content = tk.Text(right, wrap="word", font=("Segoe UI", 11), padx=12, pady=10,
                                insertwidth=0, cursor="arrow")
        self.content.pack(fill="both", expand=True, side="left")
        content_scroll = ttk.Scrollbar(right, orient="vertical", command=self.content.yview)
        content_scroll.pack(side="right", fill="y")
        self.content.configure(yscrollcommand=content_scroll.set)

        # Keep the widget in "normal" state (so text can be selected/copied
        # with the mouse and Ctrl+C) but block actual typing/editing.
        self._readonly_allowed_keys = {
            "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
            "Shift_L", "Shift_R", "Control_L", "Control_R",
        }
        self.content.bind("<Key>", self._block_typing)
        self.content.bind("<Button-3>", self._show_context_menu)

        # text tags for styling
        self.content.tag_configure("user_header", foreground="#0b5fff", font=("Segoe UI", 11, "bold"),
                                    justify="right", spacing3=4)
        self.content.tag_configure("assistant_header", foreground="#c2410c", font=("Segoe UI", 11, "bold"),
                                    justify="right", spacing3=4)
        self.content.tag_configure("user_body", justify="right", lmargin1=20, lmargin2=20,
                                    background="#eaf1ff", spacing1=4, spacing3=10)
        self.content.tag_configure("assistant_body", justify="right", lmargin1=20, lmargin2=20,
                                    background="#fff3ea", spacing1=4, spacing3=10)
        self.content.tag_configure("thinking_body", justify="right", lmargin1=20, lmargin2=20,
                                    foreground="#888888", font=("Segoe UI", 10, "italic"), spacing3=6)
        self.content.tag_configure("tool_body", justify="right", lmargin1=20, lmargin2=20,
                                    foreground="#0a7d3b", font=("Consolas", 9), spacing3=6)
        self.content.tag_configure("title", font=("Segoe UI", 14, "bold"), justify="right", spacing3=10)
        self.content.tag_configure("meta", foreground="#666666", justify="right", spacing3=10)
        self.content.tag_configure("proj_desc", justify="right", spacing3=6, font=("Segoe UI", 11))
        self.content.tag_configure("code_block", font=("Consolas", 10), foreground="#d4d4d4",
                                    background="#1e1e1e", lmargin1=20, lmargin2=20, rmargin=20,
                                    justify="left", spacing1=2, spacing3=4, wrap="none")

        self.current_conversation = None

    # ---------------- Actions ----------------

    def open_export(self):
        path = filedialog.askopenfilename(
            title="Select the Claude export .zip file",
            filetypes=[("Zip files", "*.zip"), ("All files", "*.*")]
        )
        if not path:
            # allow picking a folder instead
            path = filedialog.askdirectory(title="Or select the extracted export folder")
            if not path:
                return
        try:
            self.data.load(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load export:\n{e}")
            return

        self.filtered_conversations = list(self.data.conversations)
        self.populate_conversations()
        self.populate_projects()

        user_name = self.data.users[0].get("full_name", "") if self.data.users else ""
        self.status_var.set(
            f"{len(self.data.conversations)} conversations, {len(self.data.projects)} projects — User: {user_name}"
        )

    def populate_conversations(self):
        self.conv_list.delete(*self.conv_list.get_children())
        for idx, conv in enumerate(self.filtered_conversations):
            title = conv.get("name") or "(untitled)"
            date = fmt_date(conv.get("updated_at", ""))
            self.conv_list.insert("", "end", iid=str(idx), text=shape_rtl(title), values=(date,))

    def populate_projects(self):
        self.proj_list.delete(0, "end")
        for proj in self.data.projects:
            self.proj_list.insert("end", shape_rtl(proj.get("name", "(untitled)")))

    def apply_filter(self):
        query = self.search_var.get().strip().lower()
        if not query:
            self.filtered_conversations = list(self.data.conversations)
        else:
            result = []
            for conv in self.data.conversations:
                haystack = (conv.get("name", "") + " " + conv.get("summary", "")).lower()
                if query in haystack:
                    result.append(conv)
                    continue
                for msg in conv.get("chat_messages", []):
                    if query in (msg.get("text", "") or "").lower():
                        result.append(conv)
                        break
            self.filtered_conversations = result
        self.populate_conversations()

    def on_select_conversation(self, event=None):
        sel = self.conv_list.selection()
        if not sel:
            return
        idx = int(sel[0])
        conv = self.filtered_conversations[idx]
        self.current_conversation = conv
        self.render_conversation(conv)

    def on_select_project(self, event=None):
        sel = self.proj_list.curselection()
        if not sel:
            return
        proj = self.data.projects[sel[0]]
        self.render_project(proj)

    def show_memory(self):
        self._clear_content()
        self._insert("Claude Memory\n", "title")
        if not self.data.memories:
            self._insert("No memory data found.\n", "meta")
        else:
            mem = self.data.memories[0]
            text = mem.get("conversations_memory") or json.dumps(mem, ensure_ascii=False, indent=2)
            self._insert_rich_text(text + "\n", "proj_desc")
        self._lock_content()

    def render_project(self, proj):
        self._clear_content()
        self._insert(proj.get("name", "(untitled)") + "\n", "title")
        created = fmt_date(proj.get("created_at", ""))
        updated = fmt_date(proj.get("updated_at", ""))
        self._insert(f"Created: {created}   |   Updated: {updated}\n\n", "meta")
        desc = proj.get("description") or "(no description)"
        self._insert_rich_text(desc + "\n\n", "proj_desc")
        docs = proj.get("docs") or []
        if docs:
            self._insert(f"Attached documents ({len(docs)}):\n", "assistant_header")
            for d in docs:
                self._insert(f"- {d.get('filename', d.get('uuid',''))}\n", "meta")
        self._lock_content()

    def render_conversation(self, conv):
        self._clear_content()
        self._insert(conv.get("name", "(untitled)") + "\n", "title")
        created = fmt_date(conv.get("created_at", ""))
        updated = fmt_date(conv.get("updated_at", ""))
        self._insert(f"Created: {created}   |   Last updated: {updated}\n\n", "meta")

        for msg in conv.get("chat_messages", []):
            sender = msg.get("sender", "")
            header = "You" if sender == "human" else "Claude"
            header_tag = "user_header" if sender == "human" else "assistant_header"
            body_tag = "user_body" if sender == "human" else "assistant_body"

            self._insert(f"\n{header}:\n", header_tag)

            content_blocks = msg.get("content") or []
            if not content_blocks and msg.get("text"):
                self._insert_rich_text(msg["text"] + "\n", body_tag)
                continue

            for block in content_blocks:
                btype = block.get("type")
                if btype == "text":
                    txt = block.get("text", "")
                    if txt:
                        self._insert_rich_text(txt + "\n", body_tag)
                elif btype == "thinking":
                    txt = block.get("thinking", "")
                    if txt:
                        self._insert(f"[thinking] {txt}\n", "thinking_body")
                elif btype == "tool_use":
                    name = block.get("name", "tool")
                    self._insert(f"[used tool: {name}]\n", "tool_body")
                elif btype == "tool_result":
                    self._insert("[tool result received]\n", "tool_body")
                else:
                    # unknown block type - dump minimal info
                    self._insert(f"[{btype}]\n", "tool_body")

            files = msg.get("files") or []
            attachments = msg.get("attachments") or []
            for f in files + attachments:
                fname = f.get("file_name") or f.get("name") or "attachment"
                self._insert(f"📎 {fname}\n", "meta")

        self._lock_content()

    def open_in_browser(self):
        """Render the currently selected conversation as HTML and open it in
        the default browser. Browsers do proper bidi + Arabic/Persian glyph
        shaping natively, so this always renders correctly - including
        wrapped, multi-line paragraphs, which the in-app viewer can't
        perfectly handle."""
        if not self.current_conversation:
            messagebox.showinfo("Notice", "Select a conversation from the list first.")
            return
        html_content = build_conversation_html(self.current_conversation)
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
        tmp.write(html_content)
        tmp.close()
        webbrowser.open("file://" + tmp.name)

    def export_current_conversation(self):
        if not self.current_conversation:
            messagebox.showinfo("Notice", "Select a conversation first.")
            return
        conv = self.current_conversation
        default_name = (conv.get("name") or "conversation").replace("/", "-") + ".txt"
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=default_name,
                                             filetypes=[("Text file", "*.txt")])
        if not path:
            return
        lines = [conv.get("name", ""), ""]
        for msg in conv.get("chat_messages", []):
            header = "You" if msg.get("sender") == "human" else "Claude"
            lines.append(f"--- {header} ---")
            for block in msg.get("content") or []:
                if block.get("type") == "text":
                    lines.append(block.get("text", ""))
                elif block.get("type") == "thinking":
                    lines.append(f"[thinking] {block.get('thinking','')}")
            lines.append("")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        messagebox.showinfo("Done", f"Conversation saved to:\n{path}")

    # ---------------- content widget helpers ----------------

    def _clear_content(self):
        self.content.delete("1.0", "end")

    def _insert(self, text, tag):
        self.content.insert("end", shape_rtl(text), tag)

    def _lock_content(self):
        # kept as a no-op for backwards compatibility with call sites;
        # the widget stays selectable/copyable at all times (see _block_typing)
        pass

    def _block_typing(self, event):
        """Allow navigation and copy shortcuts, block anything that would
        modify the (read-only) text."""
        ctrl_held = (event.state & 0x4) != 0
        if ctrl_held and event.keysym.lower() in ("c", "a", "insert"):
            return None
        if event.keysym in self._readonly_allowed_keys:
            return None
        return "break"

    def _show_context_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Copy", command=self._copy_selection)
        menu.add_command(label="Select All", command=self._select_all_content)
        menu.tk_popup(event.x_root, event.y_root)

    def _select_all_content(self):
        self.content.tag_add("sel", "1.0", "end")

    def _copy_selection(self):
        try:
            selected = self.content.get("sel.first", "sel.last")
        except tk.TclError:
            return
        self._copy_to_clipboard(selected)

    def _copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    # Matches ```lang\ncode``` fenced blocks, same syntax Claude.ai uses
    _CODE_FENCE_RE = re.compile(r"```(\w*)\n?(.*?)```", re.DOTALL)

    def _insert_rich_text(self, text, body_tag):
        """Insert text, rendering fenced ```code``` blocks as distinct,
        individually-copyable code blocks (like the Claude.ai code panes)."""
        if not text:
            return
        pos = 0
        for m in self._CODE_FENCE_RE.finditer(text):
            before = text[pos:m.start()]
            if before:
                self._insert(before, body_tag)
            self._insert_code_block(m.group(2), m.group(1))
            pos = m.end()
        remainder = text[pos:]
        if remainder:
            self._insert(remainder, body_tag)

    def _insert_code_block(self, code, lang):
        code = code.rstrip("\n")

        bar = tk.Frame(self.content, bg="#2d2d2d")
        lang_label = tk.Label(bar, text=(lang or "code"), bg="#2d2d2d", fg="#9da5b4",
                               font=("Consolas", 9), anchor="w")
        lang_label.pack(side="left", padx=8, pady=3)
        copy_btn = tk.Button(bar, text="Copy", font=("Segoe UI", 8), relief="flat",
                              bg="#3c3c3c", fg="white", activebackground="#4a4a4a",
                              activeforeground="white", bd=0, padx=8,
                              command=lambda c=code: self._copy_code(c, copy_btn_ref))
        copy_btn.pack(side="right", padx=6, pady=3)
        copy_btn_ref = copy_btn  # allow the button to update its own label

        self.content.window_create("end", window=bar)
        self.content.insert("end", "\n")
        self.content.insert("end", code + "\n", "code_block")

    def _copy_code(self, code, button):
        self._copy_to_clipboard(code)
        original = button.cget("text")
        button.configure(text="Copied!")
        self.root.after(1200, lambda: button.configure(text=original) if button.winfo_exists() else None)


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    app = ViewerApp(root)

    # allow passing a zip/folder path as first CLI argument
    if len(sys.argv) > 1:
        try:
            app.data.load(sys.argv[1])
            app.filtered_conversations = list(app.data.conversations)
            app.populate_conversations()
            app.populate_projects()
            user_name = app.data.users[0].get("full_name", "") if app.data.users else ""
            app.status_var.set(
                f"{len(app.data.conversations)} conversations, {len(app.data.projects)} projects — User: {user_name}"
            )
        except Exception as e:
            print("Failed to load input file:", e)

    root.mainloop()


if __name__ == "__main__":
    main()
