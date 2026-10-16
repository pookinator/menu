#!/usr/bin/env python3
"""Interactive GUI editor for menu.json."""

from __future__ import annotations

import json
import mimetypes
import re
import shutil
import tkinter as tk
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse

try:
    from PIL import Image, ImageGrab, ImageTk

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

ROOT_DIR = Path(__file__).resolve().parent
MENU_PATH = ROOT_DIR / "menu.json"
IMAGES_DIR = ROOT_DIR / "images"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())
    return slug.strip("-")


def ensure_images_dir() -> None:
    IMAGES_DIR.mkdir(exist_ok=True)


def image_menu_reference(path: Path) -> str:
    return path.relative_to(ROOT_DIR).as_posix()


def guess_suffix_from_url(url: str, content_type: str | None = None) -> str:
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return ".jpg" if guessed == ".jpe" else guessed
    path_suffix = Path(urlparse(url).path).suffix.lower()
    if path_suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if path_suffix == ".jpeg" else path_suffix
    return ".jpg"


def next_image_path(stem: str, suffix: str) -> Path:
    ensure_images_dir()
    safe_stem = slugify(stem) or "image"
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    candidate = IMAGES_DIR / f"{safe_stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = IMAGES_DIR / f"{safe_stem}-{counter}{suffix}"
        counter += 1
    return candidate


def download_image(url: str, stem: str) -> Path:
    request = urllib.request.Request(
        url, headers={"User-Agent": "PookinatorMenuEditor/1.0"}
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
        content_type = response.headers.get_content_type()
    suffix = guess_suffix_from_url(url, content_type)
    destination = next_image_path(stem, suffix)
    destination.write_bytes(data)
    return destination


def import_image_file(source: Path, stem: str) -> Path:
    suffix = source.suffix.lower() or ".png"
    destination = next_image_path(stem, suffix)
    shutil.copy2(source, destination)
    return destination


def save_clipboard_image(stem: str) -> Path:
    if not HAS_PIL:
        raise RuntimeError(
            "Clipboard images need Pillow. Install with: pip install pillow"
        )
    clipboard = ImageGrab.grabclipboard()
    if clipboard is None:
        raise ValueError("No image found on the clipboard.")
    if isinstance(clipboard, Image.Image):
        destination = next_image_path(stem, ".png")
        rgb = clipboard.convert("RGBA")
        rgb.save(destination, format="PNG")
        return destination
    if isinstance(clipboard, list) and clipboard:
        source = Path(clipboard[0])
        if source.is_file():
            return import_image_file(source, stem)
    raise ValueError("Clipboard does not contain a usable image.")


class ImagePickerDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, item_id: str, current_path: str = "") -> None:
        super().__init__(parent)
        self.title("Select image")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.item_id = item_id or "image"
        self.result: str | None = None
        self._preview_photo: object | None = None

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Images are saved under images/ and referenced for GitHub Pages.",
            wraplength=420,
        ).pack(anchor="w", pady=(0, 8))

        self.preview_label = ttk.Label(frame, text="No preview")
        self.preview_label.pack(anchor="w", pady=(0, 8))

        url_frame = ttk.LabelFrame(frame, text="From URL", padding=8)
        url_frame.pack(fill="x", pady=(0, 8))
        self.url_var = tk.StringVar()
        ttk.Entry(url_frame, textvariable=self.url_var).pack(fill="x", pady=(0, 6))
        ttk.Button(url_frame, text="Download to images/", command=self._use_url).pack(
            anchor="w"
        )

        clip_frame = ttk.LabelFrame(frame, text="From clipboard", padding=8)
        clip_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(
            clip_frame,
            text="Copy a screenshot (Win+Shift+S), then paste it here.",
            wraplength=420,
        ).pack(anchor="w", pady=(0, 6))
        ttk.Button(
            clip_frame, text="Paste screenshot from clipboard", command=self._use_clipboard
        ).pack(anchor="w")

        ttk.Button(frame, text="Choose file from computer…", command=self._choose_file).pack(
            anchor="w", pady=(0, 8)
        )

        if current_path:
            ttk.Label(frame, text=f"Current: {current_path}", wraplength=420).pack(
                anchor="w", pady=(0, 8)
            )

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")

        self._show_preview(current_path)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Control-v>", self._on_paste_shortcut)
        self.wait_window()

    def _finish(self, menu_path: str) -> None:
        self.result = menu_path
        self.destroy()

    def _show_preview(self, menu_path: str) -> None:
        self.preview_label.configure(text="No preview", image="")
        self._preview_photo = None
        if not menu_path or not HAS_PIL:
            if menu_path:
                self.preview_label.configure(text=menu_path)
            return
        if menu_path.startswith(("http://", "https://")):
            self.preview_label.configure(text=menu_path)
            return
        candidate = (ROOT_DIR / Path(menu_path)).resolve()
        if not candidate.is_file():
            self.preview_label.configure(text=menu_path)
            return
        try:
            image = Image.open(candidate)
            image.thumbnail((220, 140))
            self._preview_photo = ImageTk.PhotoImage(image)
            self.preview_label.configure(image=self._preview_photo, text="")
        except OSError:
            self.preview_label.configure(text=menu_path)

    def _use_url(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Image", "Paste an image URL first.", parent=self)
            return
        if not url.startswith(("http://", "https://")):
            messagebox.showerror("Image", "URL must start with http:// or https://", parent=self)
            return
        try:
            saved = download_image(url, self.item_id)
        except (urllib.error.URLError, ValueError, OSError) as exc:
            messagebox.showerror("Image", f"Could not download image:\n{exc}", parent=self)
            return
        self._finish(image_menu_reference(saved))

    def _use_clipboard(self) -> None:
        try:
            saved = save_clipboard_image(self.item_id)
        except (RuntimeError, ValueError, OSError) as exc:
            messagebox.showerror("Image", str(exc), parent=self)
            return
        self._finish(image_menu_reference(saved))

    def _choose_file(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Choose image",
            filetypes=[
                ("Images", "*.png;*.jpg;*.jpeg;*.webp;*.gif"),
                ("All files", "*.*"),
            ],
        )
        if not chosen:
            return
        try:
            saved = import_image_file(Path(chosen), self.item_id)
        except OSError as exc:
            messagebox.showerror("Image", f"Could not import image:\n{exc}", parent=self)
            return
        self._finish(image_menu_reference(saved))

    def _on_paste_shortcut(self, _event: tk.Event) -> str:
        widget = self.focus_get()
        if isinstance(widget, (tk.Entry, ttk.Entry)):
            return "break"
        self._use_clipboard()
        return "break"


class CustomizationDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, data: dict | None = None) -> None:
        super().__init__(parent)
        self.title("Customization")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: dict | None = None

        data = data or {}
        self.name_var = tk.StringVar(value=data.get("name", ""))
        self.type_var = tk.StringVar(value=data.get("type", "single"))

        frame = ttk.Frame(self, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.name_var, width=40).grid(
            row=0, column=1, sticky="ew", pady=(0, 8)
        )

        ttk.Label(frame, text="Type").grid(row=1, column=0, sticky="w")
        ttk.Combobox(
            frame,
            textvariable=self.type_var,
            values=("single", "multi"),
            state="readonly",
            width=37,
        ).grid(row=1, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Options (one per line)").grid(
            row=2, column=0, columnspan=2, sticky="w"
        )
        self.options_text = tk.Text(frame, width=44, height=8, wrap="word")
        self.options_text.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        options = data.get("options") or []
        self.options_text.insert("1.0", "\n".join(options))

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text="Save", command=self._save).grid(row=0, column=1)

        frame.columnconfigure(1, weight=1)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.wait_window()

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Customization", "Name is required.", parent=self)
            return
        options = [
            line.strip()
            for line in self.options_text.get("1.0", "end").splitlines()
            if line.strip()
        ]
        if not options:
            messagebox.showerror("Customization", "Add at least one option.", parent=self)
            return
        self.result = {
            "name": name,
            "type": self.type_var.get(),
            "options": options,
        }
        self.destroy()


class MenuEditor(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Pookinator Menu Editor")
        self.geometry("980x640")
        self.minsize(860, 520)

        self.menu_data: dict = {"items": []}
        self.items: list[dict] = []
        self.current_index: int | None = None
        self.dirty = False

        self._build_ui()
        self._load_menu()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        toolbar = ttk.Frame(root)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="Save menu.json", command=self._save_menu).pack(side="left")
        ttk.Button(toolbar, text="Reload", command=self._reload).pack(side="left", padx=(6, 0))
        self.status_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self.status_var).pack(side="right")

        paned = ttk.Panedwindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=(0, 0, 8, 0))
        paned.add(left, weight=1)

        ttk.Label(left, text="Menu items").pack(anchor="w")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._refresh_list())
        filter_row = ttk.Frame(left)
        filter_row.pack(fill="x", pady=(4, 6))
        ttk.Label(filter_row, text="Filter").pack(side="left")
        ttk.Entry(filter_row, textvariable=self.filter_var).pack(
            side="left", fill="x", expand=True, padx=(6, 0)
        )

        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self.item_list = tk.Listbox(list_frame, exportselection=False)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.item_list.yview)
        self.item_list.configure(yscrollcommand=scroll.set)
        self.item_list.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.item_list.bind("<<ListboxSelect>>", self._on_select_item)

        list_buttons = ttk.Frame(left)
        list_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(list_buttons, text="New", command=self._new_item).pack(side="left")
        ttk.Button(list_buttons, text="Duplicate", command=self._duplicate_item).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(list_buttons, text="Delete", command=self._delete_item).pack(
            side="left", padx=(6, 0)
        )

        right = ttk.Frame(paned, padding=(8, 0, 0, 0))
        paned.add(right, weight=2)

        form = ttk.LabelFrame(right, text="Item details", padding=10)
        form.pack(fill="x")

        self.vars = {
            "id": tk.StringVar(),
            "name": tk.StringVar(),
            "category": tk.StringVar(),
            "prepTime": tk.StringVar(),
            "image": tk.StringVar(),
            "description": tk.StringVar(),
            "tags": tk.StringVar(),
            "active": tk.BooleanVar(value=True),
        }
        for key in self.vars:
            if key != "active":
                self.vars[key].trace_add("write", self._on_field_change)
        self.vars["active"].trace_add("write", self._on_field_change)

        rows = [
            ("ID", "id"),
            ("Name", "name"),
            ("Category", "category"),
            ("Prep time", "prepTime"),
            ("Tags (comma-separated)", "tags"),
        ]
        for row, (label, key) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(form, textvariable=self.vars[key]).grid(
                row=row, column=1, sticky="ew", pady=2
            )

        ttk.Label(form, text="Image").grid(row=len(rows), column=0, sticky="w", pady=2)
        image_field = ttk.Frame(form)
        image_field.grid(row=len(rows), column=1, sticky="ew", pady=2)
        ttk.Entry(image_field, textvariable=self.vars["image"]).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(image_field, text="Select…", command=self._pick_image).pack(
            side="left", padx=(6, 0)
        )

        description_row = len(rows) + 1
        ttk.Label(form, text="Description").grid(
            row=description_row, column=0, sticky="nw", pady=2
        )
        self.description_text = tk.Text(form, height=4, wrap="word")
        self.description_text.grid(row=description_row, column=1, sticky="ew", pady=2)
        self.description_text.bind("<KeyRelease>", self._on_field_change)

        ttk.Checkbutton(form, text="Active on menu", variable=self.vars["active"]).grid(
            row=description_row + 1, column=1, sticky="w", pady=(4, 0)
        )
        form.columnconfigure(1, weight=1)

        cust_frame = ttk.LabelFrame(right, text="Customizations", padding=10)
        cust_frame.pack(fill="both", expand=True, pady=(10, 0))

        cust_toolbar = ttk.Frame(cust_frame)
        cust_toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(cust_toolbar, text="Add", command=self._add_customization).pack(side="left")
        ttk.Button(cust_toolbar, text="Edit", command=self._edit_customization).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(cust_toolbar, text="Remove", command=self._remove_customization).pack(
            side="left", padx=(6, 0)
        )

        tree_frame = ttk.Frame(cust_frame)
        tree_frame.pack(fill="both", expand=True)
        self.cust_tree = ttk.Treeview(
            tree_frame, columns=("name", "type", "options"), show="headings", height=8
        )
        self.cust_tree.heading("name", text="Name")
        self.cust_tree.heading("type", text="Type")
        self.cust_tree.heading("options", text="Options")
        self.cust_tree.column("name", width=120, anchor="w")
        self.cust_tree.column("type", width=80, anchor="w")
        self.cust_tree.column("options", width=320, anchor="w")
        cust_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.cust_tree.yview)
        self.cust_tree.configure(yscrollcommand=cust_scroll.set)
        self.cust_tree.pack(side="left", fill="both", expand=True)
        cust_scroll.pack(side="right", fill="y")

        self.customizations: list[dict] = []

    def _set_status(self, message: str) -> None:
        suffix = " (unsaved changes)" if self.dirty else ""
        self.status_var.set(f"{message}{suffix}")

    def _load_menu(self) -> None:
        if not MENU_PATH.exists():
            messagebox.showerror("Error", f"Could not find {MENU_PATH}")
            return
        with MENU_PATH.open(encoding="utf-8") as handle:
            self.menu_data = json.load(handle)
        self.items = self.menu_data.get("items", [])
        self._refresh_list()
        self._set_status(f"Loaded {len(self.items)} items from {MENU_PATH.name}")

    def _reload(self) -> None:
        if self.dirty and not messagebox.askyesno(
            "Reload", "Discard unsaved changes and reload from disk?"
        ):
            return
        self.dirty = False
        self.current_index = None
        self._load_menu()
        self._clear_form()

    def _refresh_list(self) -> None:
        query = self.filter_var.get().strip().lower()
        self.item_list.delete(0, "end")
        self._visible_indices: list[int] = []
        for index, item in enumerate(self.items):
            label = item.get("name") or item.get("id") or f"Item {index + 1}"
            haystack = " ".join(
                [
                    label,
                    item.get("id", ""),
                    item.get("category", ""),
                    " ".join(item.get("tags") or []),
                ]
            ).lower()
            if query and query not in haystack:
                continue
            active = item.get("active", True)
            prefix = "" if active else "[inactive] "
            self.item_list.insert("end", f"{prefix}{label}")
            self._visible_indices.append(index)

    def _clear_form(self) -> None:
        self.current_index = None
        for key, var in self.vars.items():
            if key == "active":
                var.set(True)
            else:
                var.set("")
        self.description_text.delete("1.0", "end")
        self.customizations = []
        self._refresh_customization_tree()

    def _on_select_item(self, _event: tk.Event | None = None) -> None:
        if self.dirty and self.current_index is not None:
            if not messagebox.askyesno(
                "Unsaved changes", "Save changes to the current item before switching?"
            ):
                self.item_list.selection_clear(0, "end")
                if self.current_index in getattr(self, "_visible_indices", []):
                    pos = self._visible_indices.index(self.current_index)
                    self.item_list.selection_set(pos)
                    self.item_list.activate(pos)
                return
            if not self._apply_form_to_item():
                return

        selection = self.item_list.curselection()
        if not selection:
            return
        self.current_index = self._visible_indices[selection[0]]
        self._load_item_into_form(self.items[self.current_index])
        self.dirty = False
        self._set_status("Editing item")

    def _load_item_into_form(self, item: dict) -> None:
        self.vars["id"].set(item.get("id", ""))
        self.vars["name"].set(item.get("name", ""))
        self.vars["category"].set(item.get("category", ""))
        self.vars["prepTime"].set(item.get("prepTime", ""))
        self.vars["image"].set(item.get("image", ""))
        self.vars["tags"].set(", ".join(item.get("tags") or []))
        self.vars["active"].set(bool(item.get("active", True)))
        self.description_text.delete("1.0", "end")
        self.description_text.insert("1.0", item.get("description", ""))
        self.customizations = deepcopy(item.get("customizations") or [])
        self._refresh_customization_tree()

    def _on_field_change(self, *_args: object) -> None:
        if self.current_index is None:
            return
        self.dirty = True
        self._set_status("Editing item")

    def _pick_image(self) -> None:
        if self.current_index is None:
            messagebox.showinfo("Image", "Select or create an item first.")
            return
        item_id = self.vars["id"].get().strip() or slugify(self.vars["name"].get()) or "image"
        dialog = ImagePickerDialog(
            self, item_id=item_id, current_path=self.vars["image"].get().strip()
        )
        if dialog.result:
            self.vars["image"].set(dialog.result)
            self._on_field_change()

    def _refresh_customization_tree(self) -> None:
        for row in self.cust_tree.get_children():
            self.cust_tree.delete(row)
        for index, choice in enumerate(self.customizations):
            options = ", ".join(choice.get("options") or [])
            self.cust_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(choice.get("name", ""), choice.get("type", ""), options),
            )

    def _add_customization(self) -> None:
        if self.current_index is None:
            messagebox.showinfo("Customizations", "Select or create an item first.")
            return
        dialog = CustomizationDialog(self)
        if dialog.result:
            self.customizations.append(dialog.result)
            self._refresh_customization_tree()
            self._on_field_change()

    def _edit_customization(self) -> None:
        if self.current_index is None:
            return
        selected = self.cust_tree.selection()
        if not selected:
            messagebox.showinfo("Customizations", "Select a customization to edit.")
            return
        index = int(selected[0])
        dialog = CustomizationDialog(self, self.customizations[index])
        if dialog.result:
            self.customizations[index] = dialog.result
            self._refresh_customization_tree()
            self._on_field_change()

    def _remove_customization(self) -> None:
        if self.current_index is None:
            return
        selected = self.cust_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        if messagebox.askyesno("Remove customization", "Remove this customization?"):
            del self.customizations[index]
            self._refresh_customization_tree()
            self._on_field_change()

    def _item_from_form(self) -> dict:
        item: dict = {}
        item_id = self.vars["id"].get().strip()
        name = self.vars["name"].get().strip()
        if not item_id:
            raise ValueError("ID is required.")
        if not name:
            raise ValueError("Name is required.")

        item["id"] = item_id
        item["name"] = name
        category = self.vars["category"].get().strip()
        if category:
            item["category"] = category
        prep = self.vars["prepTime"].get().strip()
        if prep:
            item["prepTime"] = prep
        image = self.vars["image"].get().strip()
        if image:
            item["image"] = image
        description = self.description_text.get("1.0", "end").strip()
        if description:
            item["description"] = description

        tags = [part.strip() for part in self.vars["tags"].get().split(",") if part.strip()]
        if tags:
            item["tags"] = tags
        item["active"] = bool(self.vars["active"].get())
        if self.customizations:
            item["customizations"] = deepcopy(self.customizations)
        return item

    def _apply_form_to_item(self) -> bool:
        if self.current_index is None:
            return True
        try:
            updated = self._item_from_form()
        except ValueError as exc:
            messagebox.showerror("Validation", str(exc))
            return False

        new_id = updated["id"]
        for index, existing in enumerate(self.items):
            if index != self.current_index and existing.get("id") == new_id:
                messagebox.showerror("Validation", f"Another item already uses id '{new_id}'.")
                return False

        self.items[self.current_index] = updated
        self.dirty = False
        self._refresh_list()
        if self.current_index in self._visible_indices:
            pos = self._visible_indices.index(self.current_index)
            self.item_list.selection_set(pos)
            self.item_list.activate(pos)
        return True

    def _new_item(self) -> None:
        if self.dirty and self.current_index is not None:
            if messagebox.askyesno("Unsaved changes", "Save the current item first?"):
                if not self._apply_form_to_item():
                    return
        new_item = {
            "id": "new-item",
            "name": "New Item",
            "description": "",
            "active": True,
        }
        self.items.append(new_item)
        self.current_index = len(self.items) - 1
        self._refresh_list()
        pos = self._visible_indices.index(self.current_index)
        self.item_list.selection_clear(0, "end")
        self.item_list.selection_set(pos)
        self.item_list.activate(pos)
        self._load_item_into_form(new_item)
        self.dirty = True
        self._set_status("New item")

    def _duplicate_item(self) -> None:
        if self.current_index is None:
            messagebox.showinfo("Duplicate", "Select an item to duplicate.")
            return
        if not self._apply_form_to_item():
            return
        source = deepcopy(self.items[self.current_index])
        base_id = source.get("id", "item")
        base_name = source.get("name", "Item")
        source["id"] = f"{base_id}-copy"
        source["name"] = f"{base_name} (copy)"
        n = 2
        existing_ids = {item.get("id") for item in self.items}
        while source["id"] in existing_ids:
            source["id"] = f"{base_id}-copy-{n}"
            n += 1
        self.items.append(source)
        self.current_index = len(self.items) - 1
        self._refresh_list()
        pos = self._visible_indices.index(self.current_index)
        self.item_list.selection_set(pos)
        self.item_list.activate(pos)
        self._load_item_into_form(source)
        self.dirty = True
        self._set_status("Duplicated item")

    def _delete_item(self) -> None:
        if self.current_index is None:
            messagebox.showinfo("Delete", "Select an item to delete.")
            return
        name = self.items[self.current_index].get("name", "this item")
        if not messagebox.askyesno("Delete item", f"Delete '{name}'?"):
            return
        del self.items[self.current_index]
        self.current_index = None
        self.dirty = True
        self._clear_form()
        self._refresh_list()
        self._set_status("Item deleted")

    def _save_menu(self) -> None:
        if self.current_index is not None and not self._apply_form_to_item():
            return
        payload = {"items": self.items}
        with MENU_PATH.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        self.dirty = False
        self._set_status(f"Saved {len(self.items)} items")

    def _on_close(self) -> None:
        if self.dirty:
            if messagebox.askyesno("Quit", "Save changes before quitting?"):
                self._save_menu()
        self.destroy()


def main() -> None:
    app = MenuEditor()
    app.mainloop()


if __name__ == "__main__":
    main()
