import tkinter as tk
from tkinter import scrolledtext, filedialog, ttk, messagebox
import subprocess
import threading
import base64
import re
import os
import json
import io
import webbrowser
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

C = {
    "bg":           "#0d0d12",
    "bg_card":      "#13131c",
    "bg_input":     "#1a1a26",
    "bg_hover":     "#1f1f2e",
    "bg_selected":  "#1e1a3a",
    "border":       "#252535",
    "border_dim":   "#1c1c28",
    "accent":       "#534AB7",
    "accent_hov":   "#6058c8",
    "accent_dim":   "#2a2460",
    "text":         "#d0d0e8",
    "text_muted":   "#8888aa",
    "text_dim":     "#44445a",
    "green":        "#1D9E75",
    "amber":        "#BA7517",
    "red":          "#c0392b",
    "tag_bg":       "#1e1a3a",
    "tag_fg":       "#8880d0",
}

accounts = {
    'adgjl1182': 'UUVUVU85OTk5OQ==',
}
passwords = {a: base64.b64decode(v).decode() for a, v in accounts.items()}

save_location = "Not set"
steam_api_key = ""
wallpapers = []
selected_wp = None
thumbnail_cache = {}

ws_items = []
ws_selected_idx = None
ws_selected_data = None
ws_page = 1

def load_settings():
    global save_location, steam_api_key
    try:
        with open('lastsavelocation.cfg') as f:
            d = f.read().strip()
            if '|' in d:
                path_part, key_part = d.split('|', 1)
                save_location = path_part if os.path.isdir(path_part) else "Not set"
                steam_api_key = key_part
            else:
                save_location = d if os.path.isdir(d) else "Not set"
    except FileNotFoundError:
        save_location = "Not set"

def save_settings():
    with open('lastsavelocation.cfg', 'w') as f:
        f.write(f"{save_location}|{steam_api_key}")

def scan_wallpapers():
    global wallpapers
    wallpapers = []
    if save_location == "Not set":
        return
    mp = Path(save_location) / "projects" / "myprojects"
    if not mp.is_dir():
        return
    for folder in sorted(mp.iterdir()):
        if not folder.is_dir():
            continue
        wp = {
            "id":       folder.name,
            "title":    folder.name,
            "type":     "Unknown",
            "tags":     [],
            "preview":  None,
            "path":     str(folder),
            "size_mb":  0.0,
        }
        proj_file = folder / "project.json"
        if proj_file.exists():
            try:
                with open(proj_file, encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                wp["title"] = data.get("title", folder.name)
                wp["type"]  = data.get("type", "Unknown").capitalize()
                wp["tags"]  = data.get("tags", [])
                for ext in ("preview.gif", "preview.png", "preview.jpg",
                            "preview.jpeg", "thumbnail.png", "thumbnail.jpg"):
                    p = folder / ext
                    if p.exists():
                        wp["preview"] = str(p)
                        break
            except Exception:
                pass
        try:
            total = sum(f.stat().st_size for f in folder.rglob('*') if f.is_file())
            wp["size_mb"] = total / (1024 * 1024)
        except Exception:
            pass
        wallpapers.append(wp)

def gui_call(func, *args, **kwargs):
    root.after(0, lambda: func(*args, **kwargs))

def get_thumbnail(path, size=(80, 45)):
    if not HAS_PIL or not path or not os.path.exists(path):
        return None
    if path in thumbnail_cache:
        return thumbnail_cache[path]
    try:
        img = Image.open(path)
        if getattr(img, "is_animated", False):
            img.seek(0)
        img = img.convert("RGBA")
        img.thumbnail(size, Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        thumbnail_cache[path] = photo
        return photo
    except Exception:
        return None

def get_detailed_preview(path, size=(200, 150)):
    if not HAS_PIL or not path or not os.path.exists(path):
        return None
    try:
        img = Image.open(path)
        if getattr(img, "is_animated", False):
            img.seek(0)
        img = img.convert("RGBA")
        img.thumbnail(size, Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None

ws_thumb_cache = {}

def download_thumbnail(url):
    if not HAS_REQUESTS or not url:
        return None
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None
        return r.content
    except:
        return None

def create_thumbnail_from_bytes(data, size=(120, 120)):
    if not HAS_PIL or not data:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        if getattr(img, "is_animated", False):
            img.seek(0)
        img = img.convert("RGBA")
        img.thumbnail(size, Image.LANCZOS)
        w, h = img.size
        bg = Image.new("RGBA", size, (0, 0, 0, 0))
        offset = ((size[0] - w) // 2, (size[1] - h) // 2)
        bg.paste(img, offset, img if img.mode == "RGBA" else None)
        return ImageTk.PhotoImage(bg)
    except:
        return None

def apply_thumbnail(label, photo):
    if not label.winfo_exists():
        return
    label.config(image=photo, text="")
    label.image = photo

def load_thumbnail_async(url, label, size=(120, 120)):
    if url in ws_thumb_cache:
        photo = ws_thumb_cache[url]
        root.after(0, lambda: apply_thumbnail(label, photo))
        return

    def download():
        data = download_thumbnail(url)
        if not data:
            return
        root.after(0, lambda: create_and_apply(data, label, url, size))

    threading.Thread(target=download, daemon=True).start()

def create_and_apply(data, label, url, size):
    if not label.winfo_exists():
        return
    photo = create_thumbnail_from_bytes(data, size)
    if not photo:
        return
    ws_thumb_cache[url] = photo
    apply_thumbnail(label, photo)

root = tk.Tk()
root.title("Wallpaper Engine  ·  Workshop Manager")
root.configure(bg=C["bg"])
root.geometry("960x680")
root.minsize(820, 580)

def _btn(parent, text, cmd, color=None, width=None, icon=""):
    kwargs = dict(
        text=f"{icon}  {text}" if icon else text,
        bg=color or C["accent"],
        fg="#ffffff",
        activebackground=C["accent_hov"],
        activeforeground="#fff",
        relief="flat", bd=0, cursor="hand2",
        font=("Segoe UI", 10, "bold"),
        command=cmd,
    )
    if width:
        kwargs["width"] = width
    return tk.Button(parent, **kwargs)

def _label(parent, text, size=10, color=None, bold=False):
    weight = "bold" if bold else "normal"
    return tk.Label(parent, text=text, bg=C["bg"],
                    fg=color or C["text_muted"],
                    font=("Segoe UI", size, weight))

def _frame(parent, bg=None, **kw):
    return tk.Frame(parent, bg=bg or C["bg"], **kw)

def _input_wrap(parent, **kw):
    return tk.Frame(parent, bg=C["bg_input"], bd=0,
                    highlightbackground=C["border"],
                    highlightthickness=1, **kw)

def bind_clipboard(w):
    def copy(e=None):
        try: t = w.get("sel.first","sel.last"); w.clipboard_clear(); w.clipboard_append(t)
        except: pass
        return "break"
    def paste(e=None):
        try:
            if str(w["state"]) == "disabled": return "break"
            w.insert(tk.INSERT, w.clipboard_get())
        except: pass
        return "break"
    def cut(e=None):
        try:
            if str(w["state"]) == "disabled": return "break"
            t = w.get("sel.first","sel.last"); w.clipboard_clear(); w.clipboard_append(t)
            w.delete("sel.first","sel.last")
        except: pass
        return "break"
    def sel_all(e=None):
        w.focus_set(); w.tag_add("sel","1.0","end-1c"); w.mark_set("insert","1.0")
        return "break"
    pairs = [("<Control-c>",copy),("<Control-C>",copy),
             ("<Control-v>",paste),("<Control-V>",paste),
             ("<Control-x>",cut),("<Control-X>",cut),
             ("<Control-a>",sel_all),("<Control-A>",sel_all)]
    for k,fn in pairs:
        w.bind(k,fn)

nav_frame = tk.Frame(root, bg=C["bg_card"], width=200)
nav_frame.pack(side="left", fill="y")
nav_frame.pack_propagate(False)

tk.Label(nav_frame, text="WE Manager",
         bg=C["bg_card"], fg=C["text"],
         font=("Segoe UI", 13, "bold"),
         padx=16, pady=18, anchor="w").pack(fill="x")

tk.Frame(nav_frame, bg=C["border_dim"], height=1).pack(fill="x", padx=12)

nav_items = [
    ("Library",    "📚"),
    ("Workshop",   "🛒"),
    ("Downloader", "⬇"),
    ("Settings",   "⚙"),
]
active_tab = tk.StringVar(value="Library")
nav_buttons = {}
content_area = tk.Frame(root, bg=C["bg"])
content_area.pack(side="left", fill="both", expand=True)
pages = {}

def show_tab(name):
    active_tab.set(name)
    for n, b in nav_buttons.items():
        if n == name:
            b.config(bg=C["accent_dim"], fg=C["text"])
        else:
            b.config(bg=C["bg_card"], fg=C["text_muted"])
    for n, f in pages.items():
        f.pack_forget()
    pages[name].pack(fill="both", expand=True)
    if name == "Workshop" and not ws_items:
        threaded(ws_search)

for tab_name, icon in nav_items:
    b = tk.Button(nav_frame, text=f"  {icon}  {tab_name}",
                  bg=C["bg_card"], fg=C["text_muted"],
                  activebackground=C["accent_dim"], activeforeground=C["text"],
                  relief="flat", bd=0, cursor="hand2", anchor="w",
                  font=("Segoe UI", 10), padx=8, pady=10,
                  command=lambda n=tab_name: show_tab(n))
    b.pack(fill="x", padx=6, pady=2)
    nav_buttons[tab_name] = b

tk.Frame(nav_frame, bg=C["border_dim"], height=1).pack(side="bottom", fill="x", padx=12, pady=(0,8))
tk.Label(nav_frame, text="v1.2.6",
         bg=C["bg_card"], fg=C["text_dim"],
         font=("Segoe UI", 8)).pack(side="bottom", pady=4)

page_lib = tk.Frame(content_area, bg=C["bg"])
pages["Library"] = page_lib

lib_toolbar = _frame(page_lib, bg=C["bg_card"])
lib_toolbar.pack(fill="x")
tk.Label(lib_toolbar, text="Installed Wallpapers",
         bg=C["bg_card"], fg=C["text"],
         font=("Segoe UI", 13, "bold"), padx=16, pady=12).pack(side="left")
lib_count_label = tk.Label(lib_toolbar, text="",
                           bg=C["bg_card"], fg=C["text_muted"],
                           font=("Segoe UI", 9))
lib_count_label.pack(side="left", padx=4)

filter_row = _frame(page_lib, bg=C["bg"])
filter_row.pack(fill="x", padx=16, pady=(10, 4))
search_wrap = _input_wrap(filter_row)
search_wrap.pack(side="left", fill="x", expand=True)
tk.Label(search_wrap, text="🔍", bg=C["bg_input"], padx=6,
         font=("Segoe UI", 10)).pack(side="left")
search_var = tk.StringVar()
search_entry = tk.Entry(search_wrap, textvariable=search_var,
                        bg=C["bg_input"], fg=C["text"],
                        insertbackground=C["accent"],
                        relief="flat", bd=0,
                        font=("Segoe UI", 10))
search_entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0,8))

type_var = tk.StringVar(value="All")
type_wrap = _input_wrap(filter_row)
type_wrap.pack(side="left", padx=(8,0))
type_om = tk.OptionMenu(type_wrap, type_var, "All", "Scene", "Video", "Web", "Application", "Unknown")
type_om.config(bg=C["bg_input"], fg=C["text_muted"],
               activebackground=C["accent"], activeforeground="#fff",
               relief="flat", bd=0, font=("Segoe UI", 10),
               highlightthickness=0)
type_om["menu"].config(bg=C["bg_input"], fg=C["text"],
                       activebackground=C["accent"], activeforeground="#fff", bd=0)
type_om.pack(ipady=5, padx=6)
_btn(filter_row, "Refresh", lambda: threaded(refresh_library), C["bg_input"]).pack(
    side="left", padx=(8,0), ipady=6, ipadx=8)
tk.Frame(page_lib, bg=C["border_dim"], height=1).pack(fill="x")

lib_split = _frame(page_lib)
lib_split.pack(fill="both", expand=True)

list_panel = _frame(lib_split, bg=C["bg_card"])
list_panel.pack(side="left", fill="y", pady=0)
list_panel.pack_propagate(False)
list_panel.config(width=300)

list_canvas = tk.Canvas(list_panel, bg=C["bg_card"], bd=0,
                        highlightthickness=0, width=298)
list_scroll = tk.Scrollbar(list_panel, orient="vertical",
                           command=list_canvas.yview)
list_canvas.config(yscrollcommand=list_scroll.set)
list_scroll.pack(side="right", fill="y")
list_canvas.pack(side="left", fill="both", expand=True)
list_inner = tk.Frame(list_canvas, bg=C["bg_card"])
list_window = list_canvas.create_window((0,0), window=list_inner, anchor="nw")

def _on_list_configure(e):
    list_canvas.config(scrollregion=list_canvas.bbox("all"))
    list_canvas.itemconfig(list_window, width=list_canvas.winfo_width())
list_inner.bind("<Configure>", _on_list_configure)
list_canvas.bind("<Configure>", lambda e: list_canvas.itemconfig(list_window, width=e.width))
def _on_mousewheel(e):
    list_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
list_canvas.bind("<MouseWheel>", _on_mousewheel)

detail_panel = _frame(lib_split)
detail_panel.pack(side="left", fill="both", expand=True)
tk.Frame(lib_split, bg=C["border_dim"], width=1).place(relx=0, rely=0, relheight=1, x=300)

detail_preview_frame = tk.Frame(detail_panel, bg=C["bg"])
detail_preview_frame.pack(anchor="nw", padx=20, pady=(20,4))
detail_preview_label = tk.Label(detail_preview_frame, bg=C["bg"])
detail_preview_label.pack()

detail_title = tk.Label(detail_panel, text="Select a wallpaper",
                        bg=C["bg"], fg=C["text_muted"],
                        font=("Segoe UI", 14, "bold"),
                        wraplength=420, justify="left")
detail_title.pack(anchor="nw", padx=20, pady=(4,4))
detail_meta = tk.Label(detail_panel, text="",
                       bg=C["bg"], fg=C["text_muted"],
                       font=("Segoe UI", 9), justify="left")
detail_meta.pack(anchor="nw", padx=20, pady=(0,8))
detail_tags_frame = _frame(detail_panel)
detail_tags_frame.pack(anchor="nw", padx=20, pady=(0,12))
detail_actions = _frame(detail_panel)
detail_actions.pack(anchor="nw", padx=20, pady=(0,16))

def open_folder_btn():
    if selected_wp is None: return
    wp = wallpapers[selected_wp]
    os.startfile(wp["path"])

def open_workshop_btn():
    if selected_wp is None: return
    wp = wallpapers[selected_wp]
    wid = wp["id"]
    if wid.isdigit() and len(wid) >= 8:
        webbrowser.open(f"https://steamcommunity.com/sharedfiles/filedetails/?id={wid}")

open_folder_b = _btn(detail_actions, "Open Folder", open_folder_btn, C["bg_input"])
open_folder_b.pack(side="left", ipady=6, ipadx=10)
workshop_b = _btn(detail_actions, "View on Workshop", open_workshop_btn, C["bg_input"])
workshop_b.pack(side="left", padx=(8,0), ipady=6, ipadx=10)
delete_b = _btn(detail_actions, "Delete", lambda: delete_wallpaper(), C["red"])
delete_b.pack(side="left", padx=(8,0), ipady=6, ipadx=10)

def delete_wallpaper():
    if selected_wp is None: return
    wp = wallpapers[selected_wp]
    if messagebox.askyesno("Delete",
           f"Delete '{wp['title']}'?\nThis cannot be undone."):
        import shutil
        try:
            shutil.rmtree(wp["path"])
            printlog_dl(f"✓  Deleted: {wp['title']}\n", "ok")
        except Exception as ex:
            printlog_dl(f"⚠  Could not delete: {ex}\n", "warn")
        refresh_library()

def show_detail(idx):
    global selected_wp
    selected_wp = idx
    wp = wallpapers[idx]

    preview_path = wp.get("preview")
    if preview_path and os.path.exists(preview_path) and HAS_PIL:
        photo = get_detailed_preview(preview_path)
        if photo:
            detail_preview_label.config(image=photo)
            detail_preview_label.image = photo
        else:
            detail_preview_label.config(image='', text="🖼")
    else:
        detail_preview_label.config(image='', text="🖼")

    detail_title.config(text=wp["title"], fg=C["text"])
    size_str = f"{wp['size_mb']:.1f} MB" if wp['size_mb'] > 0 else "?"
    detail_meta.config(
        text=f"ID: {wp['id']}   ·   Type: {wp['type']}   ·   Size: {size_str}"
    )
    for w in detail_tags_frame.winfo_children():
        w.destroy()
    for tag in wp["tags"][:12]:
        tl = tk.Label(detail_tags_frame, text=tag,
                      bg=C["tag_bg"], fg=C["tag_fg"],
                      font=("Segoe UI", 8),
                      padx=6, pady=2, bd=0, relief="flat")
        tl.pack(side="left", padx=(0,4), pady=2)

list_item_frames = []

def refresh_library():
    global list_item_frames, selected_wp
    scan_wallpapers()
    filter_list()

def filter_list(*_):
    global list_item_frames
    query = search_var.get().lower()
    ftype = type_var.get()
    for w in list_inner.winfo_children():
        w.destroy()
    list_item_frames.clear()

    shown = []
    for i, wp in enumerate(wallpapers):
        if query and query not in wp["title"].lower() and query not in wp["id"]:
            continue
        if ftype != "All" and wp["type"].lower() != ftype.lower():
            continue
        shown.append((i, wp))

    lib_count_label.config(text=f"{len(shown)} / {len(wallpapers)} wallpapers")

    for list_idx, (real_idx, wp) in enumerate(shown):
        row = tk.Frame(list_inner, bg=C["bg_card"], cursor="hand2")
        row.pack(fill="x", padx=4, pady=2)

        thumb = get_thumbnail(wp["preview"])
        if thumb:
            thumb_lbl = tk.Label(row, image=thumb, bg=C["bg_card"])
            thumb_lbl.image = thumb
            thumb_lbl.pack(side="left", padx=(6,8), pady=4)
            thumb_lbl.bind("<Button-1>", lambda e, idx=real_idx, r=row: on_click_item(e, idx, r))
        else:
            ph = tk.Label(row, text="🖼", bg=C["bg_card"], fg=C["text_dim"],
                          font=("Segoe UI", 14), padx=6, pady=4)
            ph.pack(side="left", padx=(6,8), pady=4)
            ph.bind("<Button-1>", lambda e, idx=real_idx, r=row: on_click_item(e, idx, r))

        text_area = tk.Frame(row, bg=C["bg_card"])
        text_area.pack(side="left", fill="x", expand=True)

        title_text = wp["title"][:28] + ("…" if len(wp["title"]) > 28 else "")
        title_lbl = tk.Label(text_area, text=title_text,
                             bg=C["bg_card"], fg=C["text"],
                             font=("Segoe UI", 10), anchor="w", pady=2)
        title_lbl.pack(fill="x")
        title_lbl.bind("<Button-1>", lambda e, idx=real_idx, r=row: on_click_item(e, idx, r))

        bottom = tk.Frame(text_area, bg=C["bg_card"])
        bottom.pack(fill="x")
        tk.Label(bottom, text=wp["id"], bg=C["bg_card"],
                 fg=C["text_dim"], font=("Consolas", 8)).pack(side="left")
        type_colors = {
            "Scene": C["accent"], "Video": C["green"],
            "Web": "#c0932a", "Application": C["text_muted"]
        }
        tc = type_colors.get(wp["type"], C["text_dim"])
        type_lbl = tk.Label(bottom, text=wp["type"], bg=C["bg_card"],
                            fg=tc, font=("Segoe UI", 8, "bold"))
        type_lbl.pack(side="right")
        for child in (bottom, title_lbl, type_lbl):
            child.bind("<Button-1>", lambda e, idx=real_idx, r=row: on_click_item(e, idx, r))

        sep = tk.Frame(row, bg=C["border_dim"], height=1)
        sep.pack(fill="x", side="bottom")
        row.bind("<Button-1>", lambda e, idx=real_idx, r=row: on_click_item(e, idx, r))
        list_item_frames.append(row)

def on_click_item(event, idx, row):
    for fr in list_item_frames:
        fr.config(bg=C["bg_card"])
        for child in fr.winfo_children():
            try: child.config(bg=C["bg_card"])
            except: pass
    row.config(bg=C["bg_selected"])
    for child in row.winfo_children():
        try: child.config(bg=C["bg_selected"])
        except: pass
    show_detail(idx)

search_var.trace_add("write", filter_list)
type_var.trace_add("write", filter_list)

page_ws = tk.Frame(content_area, bg=C["bg"])
pages["Workshop"] = page_ws

ws_header = tk.Frame(page_ws, bg=C["bg_card"])
ws_header.pack(fill="x")
tk.Label(ws_header, text="Steam Workshop Browser",
         bg=C["bg_card"], fg=C["text"],
         font=("Segoe UI", 13, "bold"), padx=16, pady=12).pack(side="left")
tk.Frame(page_ws, bg=C["border_dim"], height=1).pack(fill="x")

ws_search_frame = _frame(page_ws)
ws_search_frame.pack(fill="x", padx=16, pady=(12,6))
ws_search_wrap = _input_wrap(ws_search_frame)
ws_search_wrap.pack(side="left", fill="x", expand=True)
tk.Label(ws_search_wrap, text="🔍", bg=C["bg_input"], padx=6,
         font=("Segoe UI", 10)).pack(side="left")
ws_search_var = tk.StringVar()
ws_search_entry = tk.Entry(ws_search_wrap, textvariable=ws_search_var,
                           bg=C["bg_input"], fg=C["text"],
                           insertbackground=C["accent"],
                           relief="flat", bd=0,
                           font=("Segoe UI", 10))
ws_search_entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0,8))

def next_page():
    global ws_page
    ws_page += 1
    threaded(ws_search)

def prev_page():
    global ws_page
    if ws_page > 1:
        ws_page -= 1
        threaded(ws_search)

def new_ws_search():
    global ws_page
    ws_page = 1
    threaded(ws_search)

ws_search_entry.bind("<Return>", lambda e: new_ws_search())
ws_search_btn = _btn(ws_search_frame, "Search", new_ws_search, C["accent"])
ws_search_btn.pack(side="left", padx=(8,0), ipady=6, ipadx=12)

_btn(ws_search_frame, "◀", prev_page, C["bg_input"]).pack(side="left", padx=(8,0), ipady=6, ipadx=8)
_btn(ws_search_frame, "▶", next_page, C["bg_input"]).pack(side="left", padx=(4,0), ipady=6, ipadx=8)

ws_split = _frame(page_ws)
ws_split.pack(fill="both", expand=True, padx=16, pady=(4,0))

LIST_WIDTH = 400
THUMB_SIZE = (120, 120)

ws_list_panel = _frame(ws_split, bg=C["bg_card"], width=LIST_WIDTH)
ws_list_panel.pack(side="left", fill="y")
ws_list_panel.pack_propagate(False)

ws_canvas = tk.Canvas(ws_list_panel, bg=C["bg_card"], bd=0,
                      highlightthickness=0, width=LIST_WIDTH-2)
ws_scroll = tk.Scrollbar(ws_list_panel, orient="vertical",
                         command=ws_canvas.yview)
ws_canvas.config(yscrollcommand=ws_scroll.set)
ws_scroll.pack(side="right", fill="y")
ws_canvas.pack(side="left", fill="both", expand=True)

ws_list_inner = tk.Frame(ws_canvas, bg=C["bg_card"])
ws_list_window = ws_canvas.create_window((0,0), window=ws_list_inner, anchor="nw")

def _ws_configure(e):
    ws_canvas.config(scrollregion=ws_canvas.bbox("all"))
    ws_canvas.itemconfig(ws_list_window, width=ws_canvas.winfo_width())
ws_list_inner.bind("<Configure>", _ws_configure)
ws_canvas.bind("<Configure>", lambda e: ws_canvas.itemconfig(ws_list_window, width=e.width))
ws_canvas.bind("<MouseWheel>", lambda e: ws_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

ws_detail_panel = _frame(ws_split)
ws_detail_panel.pack(side="left", fill="both", expand=True, padx=(16,0))

ws_detail_title = tk.Label(ws_detail_panel, text="Select an item",
                           bg=C["bg"], fg=C["text_muted"],
                           font=("Segoe UI", 14, "bold"),
                           wraplength=400, justify="left")
ws_detail_title.pack(anchor="nw", pady=(0,4))
ws_detail_meta = tk.Label(ws_detail_panel, text="",
                          bg=C["bg"], fg=C["text_muted"],
                          font=("Segoe UI", 9))
ws_detail_meta.pack(anchor="nw", pady=(0,8))
ws_detail_rating = tk.Label(ws_detail_panel, text="",
                            bg=C["bg"], fg="#FFD700",
                            font=("Segoe UI", 10))
ws_detail_rating.pack(anchor="nw", pady=(0,8))
ws_detail_desc = tk.Label(ws_detail_panel, text="",
                          bg=C["bg"], fg=C["text_muted"],
                          font=("Segoe UI", 9),
                          wraplength=400, justify="left")
ws_detail_desc.pack(anchor="nw", pady=(0,8))

ws_dl_btn = _btn(ws_detail_panel, "Download", lambda: threaded(ws_download_current), C["accent"])
ws_dl_btn.pack(anchor="nw", pady=(0,16))

ws_status = tk.Label(ws_detail_panel, text="",
                     bg=C["bg"], fg=C["text_muted"],
                     font=("Segoe UI", 9))
ws_status.pack(anchor="nw")

ws_dl_indicator = tk.Frame(page_ws, bg=C["bg_card"],
                           highlightbackground=C["accent"],
                           highlightthickness=1)

ws_dl_ind_label = tk.Label(ws_dl_indicator, text="⏳ Downloading...",
                           bg=C["bg_card"], fg=C["accent"],
                           font=("Segoe UI", 9, "bold"), padx=10, pady=6)
ws_dl_ind_label.pack()
ws_dl_ind_prog = ttk.Progressbar(ws_dl_indicator, mode="indeterminate", length=120)
ws_dl_ind_prog.pack(padx=10, pady=(0, 8))

def show_ws_download_progress():
    ws_dl_indicator.place(relx=1.0, rely=0.0, anchor="ne", x=-16, y=12)
    ws_dl_ind_prog.start()
    ws_dl_ind_label.config(text="⏳ Downloading...")

def hide_ws_download_progress():
    ws_dl_ind_prog.stop()
    ws_dl_indicator.place_forget()

def finish_download(success):
    hide_ws_download_progress()
    ws_dl_btn.config(state=tk.NORMAL)
    if success:
        ws_status.config(text="Download completed", fg=C["green"])
    else:
        ws_status.config(text="Download failed", fg=C["red"])

def ws_search():
    global ws_items

    query = ws_search_var.get().strip()
    gui_call(ws_status.config,
             text="Loading popular items..." if not query else "Searching Workshop...")
    gui_call(ws_dl_btn.config, state=tk.DISABLED)

    if not HAS_REQUESTS:
        gui_call(ws_status.config, text="Requests library not installed")
        return
    if not steam_api_key:
        gui_call(ws_status.config,
                 text="Set Steam API key in Settings first!",
                 fg=C["amber"])
        return

    api_url = "https://api.steampowered.com/IPublishedFileService/QueryFiles/v1/"
    params = {
        "key": steam_api_key,
        "appid": 431960,
        "query_type": 0,
        "search_text": query if query else "popular",
        "page": ws_page,
        "numperpage": 20,
        "return_tags": 1,
        "return_vote_data": 1,
        "return_previews": 1,
        "return_children": 0,
        "return_metadata": 1,
        "return_short_description": 1,
    }

    try:
        r = requests.get(api_url, params=params, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            gui_call(ws_status.config, text=f"HTTP {r.status_code}")
            gui_call(ws_dl_btn.config, state=tk.NORMAL)
            return
        data = r.json()
    except Exception as e:
        gui_call(ws_status.config, text=f"Connection error: {e}")
        gui_call(ws_dl_btn.config, state=tk.NORMAL)
        return

    response = data.get("response", {})
    items_raw = response.get("publishedfiledetails", [])
    new_items = []

    for item in items_raw:
        vote_data = item.get("vote_data", {})
        new_items.append({
            "id": item.get("publishedfileid", ""),
            "title": item.get("title", "Unknown"),
            "description": item.get("short_description", "") or item.get("description", ""),
            "preview_url": item.get("preview_url", ""),
            "file_size": int(item.get("file_size", 0)),
            "time_updated": item.get("time_updated", 0),
            "creator": item.get("creator", ""),
            "subscriptions": item.get("subscriptions", 0),
            "score": vote_data.get("score", 0),
            "tags": [t.get("tag", "") for t in item.get("tags", [])],
        })

    ws_items = new_items

    def finish():
        refresh_ws_list()
        if ws_items:
            ws_status.config(text=f"Page {ws_page} · Found {len(ws_items)} items", fg=C["green"])
        else:
            ws_status.config(text="No items found", fg=C["amber"])
        ws_dl_btn.config(state=tk.NORMAL)

    root.after(0, finish)

def refresh_ws_list():
    for w in ws_list_inner.winfo_children():
        w.destroy()

    for i, item in enumerate(ws_items):
        row = tk.Frame(ws_list_inner, bg=C["bg_card"], cursor="hand2")
        row.pack(fill="x", padx=4, pady=2)

        thumb_lbl = tk.Label(row, text="🖼", bg=C["bg_card"],
                             fg=C["text_dim"], font=("Segoe UI", 14))
        thumb_lbl.pack(side="left", padx=(6, 8), pady=4)

        title_lbl = tk.Label(row, text=item["title"][:40],
                             bg=C["bg_card"], fg=C["text"],
                             font=("Segoe UI", 10), anchor="w",
                             padx=8, pady=6)
        title_lbl.pack(side="left", fill="x", expand=True)

        def make_click_handler(idx, itm, r):
            def handler(event=None):
                global ws_selected_idx, ws_selected_data
                ws_selected_idx = idx
                ws_selected_data = itm
                for child in ws_list_inner.winfo_children():
                    try: child.config(bg=C["bg_card"])
                    except: pass
                r.config(bg=C["bg_selected"])
                show_ws_detail(itm)
            return handler

        click_handler = make_click_handler(i, item, row)
        row.bind("<Button-1>", click_handler)
        title_lbl.bind("<Button-1>", click_handler)
        thumb_lbl.bind("<Button-1>", click_handler)

        thumb_url = item.get("preview_url")
        if thumb_url:
            threading.Thread(target=load_thumbnail_async,
                             args=(thumb_url, thumb_lbl, THUMB_SIZE), daemon=True).start()

def show_ws_detail(item):
    ws_detail_title.config(text=item["title"], fg=C["text"])
    size_mb = item["file_size"] / (1024*1024) if item["file_size"] else 0

    meta_text = f"ID: {item['id']}   ·   Size: {size_mb:.2f} MB"
    creator_str = f"by {item.get('creator', 'Unknown')}" if item.get("creator") else ""
    if creator_str:
        meta_text += f"   ·   {creator_str}"
    if item.get("time_updated"):
        dt = datetime.fromtimestamp(item["time_updated"])
        meta_text += f"   ·   Updated: {dt.strftime('%d %b %Y')}"
    ws_detail_meta.config(text=meta_text)

    score = item.get("score", 0)
    subs = item.get("subscriptions", 0)
    subs_str = f"{subs:,} subscribers"

    if score > 0:
        stars_filled = int(round(score * 5))
        stars_empty = 5 - stars_filled
        rating_str = "★" * stars_filled + "☆" * stars_empty
        ws_detail_rating.config(text=f"{rating_str}   ·   👥 {subs_str}")
    else:
        ws_detail_rating.config(text=f"👥 {subs_str}")

    desc = item.get("description", "")
    if len(desc) > 250:
        desc = desc[:250] + "..."
    ws_detail_desc.config(text=desc)

    ws_dl_btn.config(state=tk.NORMAL)

def ws_download_current():
    if not ws_selected_data:
        return
    pid = ws_selected_data["id"]
    if save_location == "Not set" or not os.path.isdir(save_location):
        ws_status.config(text="Set wallpaper path first!", fg=C["amber"])
        return

    ws_dl_btn.config(state=tk.DISABLED)
    show_ws_download_progress()

    def task():
        ok = ws_run_command(pid)
        root.after(0, lambda: finish_download(ok))
    threading.Thread(target=task, daemon=True).start()

def ws_run_command(pubfileid):
    target_dir = Path(save_location) / "projects" / "myprojects"
    if not target_dir.is_dir():
        return False
    script_dir = os.path.dirname(os.path.abspath(__file__))
    exe = Path(script_dir) / "DepotdownloaderMod" / "DepotDownloadermod.exe"
    out_dir = target_dir / pubfileid

    cmd = [str(exe), "-app", "431960", "-pubfile", pubfileid,
           "-verify-all", "-username", username.get(),
           "-password", passwords[username.get()], "-dir", str(out_dir)]

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False

page_dl = tk.Frame(content_area, bg=C["bg"])
pages["Downloader"] = page_dl

dl_header = tk.Frame(page_dl, bg=C["bg_card"])
dl_header.pack(fill="x")
tk.Label(dl_header, text="Workshop Downloader",
         bg=C["bg_card"], fg=C["text"],
         font=("Segoe UI", 13, "bold"), padx=16, pady=12).pack(side="left")
tk.Frame(page_dl, bg=C["border_dim"], height=1).pack(fill="x")

dl_body = _frame(page_dl)
dl_body.pack(fill="both", expand=True, padx=24, pady=16)

tk.Label(dl_body, text="ACCOUNT", bg=C["bg"], fg=C["text_dim"],
         font=("Segoe UI", 8, "bold")).pack(anchor="w")
tk.Frame(dl_body, bg=C["border_dim"], height=1).pack(fill="x", pady=(3,8))

acct_row = _frame(dl_body)
acct_row.pack(fill="x", pady=(0,16))
username = tk.StringVar(root, value=list(accounts.keys())[0])
acct_wrap = _input_wrap(acct_row)
acct_wrap.pack(side="left")
tk.Label(acct_wrap, text="👤", bg=C["bg_input"], fg=C["accent"],
         font=("Segoe UI", 11), padx=6).pack(side="left")
om = tk.OptionMenu(acct_wrap, username, *accounts.keys())
om.config(bg=C["bg_input"], fg=C["text_muted"],
          activebackground=C["accent"], activeforeground="#fff",
          relief="flat", bd=0, font=("Segoe UI", 10),
          highlightthickness=0)
om["menu"].config(bg=C["bg_input"], fg=C["text"],
                  activebackground=C["accent"], activeforeground="#fff", bd=0)
om.pack(side="left", ipady=5, padx=6)

tk.Label(dl_body, text="WALLPAPER ENGINE PATH", bg=C["bg"], fg=C["text_dim"],
         font=("Segoe UI", 8, "bold")).pack(anchor="w")
tk.Frame(dl_body, bg=C["border_dim"], height=1).pack(fill="x", pady=(3,8))

path_row = _frame(dl_body)
path_row.pack(fill="x", pady=(0,16))
path_wrap = _input_wrap(path_row)
path_wrap.pack(side="left", fill="x", expand=True)
tk.Label(path_wrap, text="📁", bg=C["bg_input"], padx=6,
         font=("Segoe UI", 10)).pack(side="left")
path_label = tk.Label(path_wrap, text=f"  {save_location}",
                      bg=C["bg_input"], fg=C["text_muted"],
                      font=("Segoe UI", 9), anchor="w")
path_label.pack(side="left", fill="x", expand=True, ipady=6)

def select_save_location():
    global save_location
    selected = filedialog.askdirectory()
    if not selected: return
    target = Path(selected) / "projects" / "myprojects"
    if not target.is_dir():
        printlog_dl("⚠  Invalid path: no \\projects\\myprojects found.\n", "warn")
    else:
        save_location = selected
        path_label.config(text=f"  {selected}")
        printlog_dl(f"✓  Path set: {selected}\n", "ok")
        save_settings()

browse_btn = tk.Button(path_row, text="  Browse ",
                       bg=C["bg_input"], fg=C["text_muted"],
                       activebackground=C["accent"], activeforeground="#fff",
                       relief="flat", bd=0, cursor="hand2",
                       font=("Segoe UI", 9),
                       command=select_save_location,
                       highlightbackground=C["border"],
                       highlightthickness=1)
browse_btn.pack(side="left", padx=(8,0), ipady=6, ipadx=6)

tk.Label(dl_body, text="WORKSHOP ITEMS", bg=C["bg"], fg=C["text_dim"],
         font=("Segoe UI", 8, "bold")).pack(anchor="w")
tk.Frame(dl_body, bg=C["border_dim"], height=1).pack(fill="x", pady=(3,4))
tk.Label(dl_body, text="One item per line — paste full URLs or plain IDs",
         bg=C["bg"], fg=C["text_dim"], font=("Segoe UI", 8)).pack(anchor="w", pady=(0,6))

link_wrap = _input_wrap(dl_body)
link_wrap.pack(fill="x")
link_text = scrolledtext.ScrolledText(
    link_wrap, height=6, bg=C["bg_input"], fg=C["text"],
    insertbackground=C["accent"], selectbackground=C["accent"],
    selectforeground="#fff", relief="flat", bd=0,
    font=("Consolas", 10), wrap="none", highlightthickness=0
)
link_text.pack(fill="x", padx=2, pady=2)
bind_clipboard(link_text)

queue_frame = _frame(dl_body)
queue_frame.pack(fill="x", pady=(8,0))
queue_label = tk.Label(queue_frame, text="", bg=C["bg"], fg=C["text_muted"],
                       font=("Segoe UI", 9))
queue_label.pack(side="left")

prog_var = tk.DoubleVar(value=0)
prog_bar = ttk.Progressbar(dl_body, variable=prog_var, maximum=100,
                           mode="determinate", length=400)

tk.Label(dl_body, text="CONSOLE", bg=C["bg"], fg=C["text_dim"],
         font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(12,0))
tk.Frame(dl_body, bg=C["border_dim"], height=1).pack(fill="x", pady=(3,6))

con_wrap = _input_wrap(dl_body)
con_wrap.pack(fill="x")
console = scrolledtext.ScrolledText(
    con_wrap, height=8,
    bg="#0a0a0e", fg=C["text_dim"],
    insertbackground=C["accent"],
    selectbackground=C["accent"], selectforeground="#fff",
    relief="flat", bd=0, font=("Consolas", 9),
    wrap="word", highlightthickness=0
)
console.tag_config("info", foreground=C["accent"])
console.tag_config("ok",   foreground=C["green"])
console.tag_config("warn", foreground=C["amber"])
console.tag_config("dim",  foreground=C["text_dim"])
console.pack(fill="x", padx=2, pady=2)
console.config(state=tk.DISABLED)
bind_clipboard(console)

def printlog_dl(log, tag="dim"):
    console.config(state=tk.NORMAL)
    console.insert(tk.END, log, tag)
    console.yview(tk.END)
    console.config(state=tk.DISABLED)

tk.Frame(dl_body, bg=C["border_dim"], height=1).pack(fill="x", pady=(12,10))

btn_row = _frame(dl_body)
btn_row.pack(fill="x")

btn_download = tk.Button(
    btn_row, text="  ⬇  Download",
    bg=C["accent"], fg="#ffffff",
    activebackground=C["accent_hov"], activeforeground="#fff",
    relief="flat", bd=0, cursor="hand2",
    font=("Segoe UI", 11, "bold"),
    command=lambda: start_dl_thread()
)
btn_download.pack(side="left", fill="x", expand=True, ipady=9)

btn_clear = tk.Button(
    btn_row, text="Clear",
    bg=C["bg_input"], fg=C["text_muted"],
    activebackground=C["bg_hover"], activeforeground=C["text"],
    relief="flat", bd=0, cursor="hand2",
    font=("Segoe UI", 10),
    command=lambda: (link_text.delete("1.0", tk.END),
                     console.config(state=tk.NORMAL),
                     console.delete("1.0", tk.END),
                     console.config(state=tk.DISABLED))
)
btn_clear.pack(side="left", padx=(8,0), ipady=9, ipadx=16)

def run_command(pubfileid, total, current):
    printlog_dl(f"▶  [{current}/{total}]  Downloading {pubfileid}\n", "info")
    queue_label.config(text=f"Item {current} of {total}")
    if save_location == "Not set" or not os.path.isdir(save_location):
        printlog_dl("⚠  Save location not set or invalid.\n", "warn")
        return False
    target_dir = Path(save_location) / "projects" / "myprojects"
    if not target_dir.is_dir():
        printlog_dl("⚠  No \\projects\\myprojects found at path.\n", "warn")
        return False

    script_dir = os.path.dirname(os.path.abspath(__file__))
    exe = Path(script_dir) / "DepotdownloaderMod" / "DepotDownloadermod.exe"
    out_dir = target_dir / pubfileid

    cmd = [str(exe), "-app", "431960", "-pubfile", pubfileid,
           "-verify-all", "-username", username.get(),
           "-password", passwords[username.get()], "-dir", str(out_dir)]

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, creationflags=subprocess.CREATE_NO_WINDOW
    )
    for line in proc.stdout:
        printlog_dl(line, "dim")
    proc.stdout.close()
    proc.wait()
    printlog_dl(f"✓  Done: {pubfileid}\n", "ok")
    return True

def run_commands():
    btn_download.config(state=tk.DISABLED, text="  Downloading…")
    links = [l for l in link_text.get("1.0", tk.END).splitlines() if l.strip()]
    ids = []
    for link in links:
        m = re.search(r'\b\d{8,10}\b', link.strip())
        if m:
            ids.append(m.group(0))
        else:
            printlog_dl(f"⚠  Skipping invalid: {link}\n", "warn")

    total = len(ids)
    for i, pid in enumerate(ids, 1):
        pct = ((i - 1) / total) * 100
        prog_var.set(pct)
        prog_bar.pack(fill="x", pady=(0,8))
        run_command(pid, total, i)

    prog_var.set(100)
    prog_bar.pack(fill="x", pady=(0,8))
    queue_label.config(text=f"Done — {total} item(s) downloaded")
    printlog_dl(f"\n✓  All {total} items finished.\n", "ok")
    btn_download.config(state=tk.NORMAL, text="  ⬇  Download")

def start_dl_thread():
    threading.Thread(target=run_commands, daemon=True).start()

page_set = tk.Frame(content_area, bg=C["bg"])
pages["Settings"] = page_set

set_header = tk.Frame(page_set, bg=C["bg_card"])
set_header.pack(fill="x")
tk.Label(set_header, text="Settings",
         bg=C["bg_card"], fg=C["text"],
         font=("Segoe UI", 13, "bold"), padx=16, pady=12).pack(side="left")
tk.Frame(page_set, bg=C["border_dim"], height=1).pack(fill="x")

set_body = _frame(page_set)
set_body.pack(fill="both", expand=True, padx=24, pady=16)

tk.Label(set_body, text="WALLPAPER ENGINE DIRECTORY", bg=C["bg"], fg=C["text_dim"],
         font=("Segoe UI", 8, "bold")).pack(anchor="w")
tk.Frame(set_body, bg=C["border_dim"], height=1).pack(fill="x", pady=(3,8))
tk.Label(set_body, text="Root folder of Wallpaper Engine (must contain projects/myprojects).",
         bg=C["bg"], fg=C["text_muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0,6))

set_path_row = _frame(set_body)
set_path_row.pack(fill="x", pady=(0,20))
set_path_wrap = _input_wrap(set_path_row)
set_path_wrap.pack(side="left", fill="x", expand=True)
tk.Label(set_path_wrap, text="📁", bg=C["bg_input"], padx=6,
         font=("Segoe UI", 10)).pack(side="left")
set_path_label = tk.Label(set_path_wrap, text=f"  {save_location}",
                          bg=C["bg_input"], fg=C["text_muted"],
                          font=("Segoe UI", 9), anchor="w")
set_path_label.pack(side="left", fill="x", expand=True, ipady=6)

def select_path_settings():
    global save_location
    selected = filedialog.askdirectory()
    if not selected: return
    target = Path(selected) / "projects" / "myprojects"
    if not target.is_dir():
        set_status.config(text="⚠  Invalid path: no \\projects\\myprojects found.", fg=C["amber"])
    else:
        save_location = selected
        set_path_label.config(text=f"  {selected}")
        path_label.config(text=f"  {selected}")
        set_status.config(text=f"✓  Path saved.", fg=C["green"])
        save_settings()

tk.Button(set_path_row, text="  Browse ",
          bg=C["bg_input"], fg=C["text_muted"],
          activebackground=C["accent"], activeforeground="#fff",
          relief="flat", bd=0, cursor="hand2",
          font=("Segoe UI", 9), command=select_path_settings,
          highlightbackground=C["border"], highlightthickness=1
          ).pack(side="left", padx=(8,0), ipady=6, ipadx=6)

tk.Label(set_body, text="ACCOUNTS", bg=C["bg"], fg=C["text_dim"],
         font=("Segoe UI", 8, "bold")).pack(anchor="w")
tk.Frame(set_body, bg=C["border_dim"], height=1).pack(fill="x", pady=(3,8))

for acct in accounts:
    acct_card = tk.Frame(set_body, bg=C["bg_input"],
                         highlightbackground=C["border"],
                         highlightthickness=1)
    acct_card.pack(fill="x", pady=(0,6))
    tk.Label(acct_card, text="👤", bg=C["bg_input"], fg=C["accent"],
             font=("Segoe UI", 11), padx=10, pady=8).pack(side="left")
    tk.Label(acct_card, text=acct, bg=C["bg_input"], fg=C["text"],
             font=("Segoe UI", 10)).pack(side="left")
    tk.Label(acct_card, text="●●●●●●●●", bg=C["bg_input"], fg=C["text_dim"],
             font=("Segoe UI", 9)).pack(side="right", padx=10)

tk.Label(set_body, text="STEAM WEB API KEY", bg=C["bg"], fg=C["text_dim"],
         font=("Segoe UI", 8, "bold")).pack(anchor="w")
tk.Frame(set_body, bg=C["border_dim"], height=1).pack(fill="x", pady=(3,8))
tk.Label(set_body, text="Get yours at https://steamcommunity.com/dev/apikey",
         bg=C["bg"], fg=C["text_muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0,6))

api_row = _frame(set_body)
api_row.pack(fill="x", pady=(0,20))
api_wrap = _input_wrap(api_row)
api_wrap.pack(side="left", fill="x", expand=True)
tk.Label(api_wrap, text="🔑", bg=C["bg_input"], padx=6,
         font=("Segoe UI", 10)).pack(side="left")
api_var = tk.StringVar(value=steam_api_key)
api_entry = tk.Entry(api_wrap, textvariable=api_var,
                     bg=C["bg_input"], fg=C["text"],
                     insertbackground=C["accent"],
                     relief="flat", bd=0, show="*",
                     font=("Segoe UI", 10))
api_entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0,8))

def save_api_key():
    global steam_api_key
    steam_api_key = api_var.get().strip()
    save_settings()
    set_status.config(text="API key saved.", fg=C["green"])

tk.Button(api_row, text=" Save ",
          bg=C["accent"], fg="#fff",
          activebackground=C["accent_hov"], activeforeground="#fff",
          relief="flat", bd=0, cursor="hand2",
          font=("Segoe UI", 9),
          command=save_api_key
          ).pack(side="left", padx=(8,0), ipady=6, ipadx=12)

set_status = tk.Label(set_body, text="", bg=C["bg"], fg=C["green"],
                      font=("Segoe UI", 9))
set_status.pack(anchor="w", pady=(12,0))

tk.Frame(set_body, bg=C["border_dim"], height=1).pack(fill="x", pady=(20,12))
tk.Label(set_body, text="ABOUT", bg=C["bg"], fg=C["text_dim"],
         font=("Segoe UI", 8, "bold")).pack(anchor="w")
tk.Frame(set_body, bg=C["border_dim"], height=1).pack(fill="x", pady=(3,8))

about_card = tk.Frame(set_body, bg=C["bg_input"],
                      highlightbackground=C["border"], highlightthickness=1)
about_card.pack(fill="x")
tk.Label(about_card, text="WE Workshop Manager  v1.2.6",
         bg=C["bg_input"], fg=C["text"],
         font=("Segoe UI", 10, "bold"), padx=12, pady=10).pack(anchor="w")
tk.Label(about_card,
         text="Powered by DepotDownloaderMod  ·  For Wallpaper Engine (App 431960)",
         bg=C["bg_input"], fg=C["text_muted"],
         font=("Segoe UI", 8), padx=12).pack(anchor="w", pady=(0,10))

style = ttk.Style()
style.theme_use("clam")
style.configure("TProgressbar",
                troughcolor=C["bg_input"],
                background=C["accent"],
                bordercolor=C["border"],
                lightcolor=C["accent"],
                darkcolor=C["accent"])

def threaded(fn):
    threading.Thread(target=fn, daemon=True).start()

def on_closing():
    try:
        subprocess.Popen("taskkill /f /im DepotDownloadermod.exe",
                         creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass
    os._exit(0)

root.protocol("WM_DELETE_WINDOW", on_closing)

load_settings()
path_label.config(text=f"  {save_location}")
set_path_label.config(text=f"  {save_location}")
api_var.set(steam_api_key)

show_tab("Library")
threaded(refresh_library)

root.mainloop()