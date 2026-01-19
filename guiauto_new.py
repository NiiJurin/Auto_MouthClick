import os
import json
import time
import threading
import tkinter as tk
from tkinter import simpledialog, messagebox

import customtkinter as ctk
import pyautogui
from pynput import mouse, keyboard


# =========================================================
#  設定（保存先）
# =========================================================
APP_NAME = "MouseMacroCTK"
CONFIG_NAME = "config.json"
MACROS_DIR = "macros"


def get_app_folder():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, APP_NAME)
    os.makedirs(folder, exist_ok=True)
    return folder


def get_config_path():
    return os.path.join(get_app_folder(), CONFIG_NAME)


def get_macros_folder():
    folder = os.path.join(get_app_folder(), MACROS_DIR)
    os.makedirs(folder, exist_ok=True)
    return folder


DEFAULT_HOTKEYS = {
    "record_start": "F1",
    "record_stop":  "F2",
    "replay_start": "F3",
    "force_stop":   "F4",   # 録画も再生も全部止める
    "quit":         "Esc",
}

DEFAULTS = {
    "loop_count": 1,
    "hotkeys": dict(DEFAULT_HOTKEYS),
    "current_macro": "default"
}


# =========================================================
#  グローバル状態
# =========================================================
recorded_clicks = []   # [(elapsed, x, y), ...]
recording = False
replaying = False
last_click_time = None

current_macro_name = DEFAULTS["current_macro"]
selected_macro_name = None

lock = threading.Lock()
stop_event = threading.Event()

mouse_listener = None
keyboard_listener = None

app = None
log_box = None
loop_var = None

badge_record = None
badge_replay = None

macro_listbox = None
current_macro_label = None

# Hotkey
hotkeys = dict(DEFAULT_HOTKEYS)   # action -> "F1" 等
hotkey_sets = {}                 # action -> set(tokens)
pressed_tokens = set()           # 現在押されてる token

entries = {}  # action -> CTkEntry widget


# =========================================================
#  ログ（GUIスレッド安全）
# =========================================================
def append_log(msg: str):
    print(msg)
    if app is None or log_box is None:
        return

    def _write():
        log_box.configure(state="normal")
        log_box.insert("end", msg + "\n")
        log_box.see("end")
        log_box.configure(state="disabled")

    app.after(0, _write)


# =========================================================
#  状態バッジ更新
# =========================================================
def update_badges():
    if badge_record is None or badge_replay is None:
        return

    if recording:
        badge_record.configure(text="● REC", fg_color="#C0392B")
    else:
        badge_record.configure(text="REC", fg_color="#3A3A3A")

    if replaying:
        badge_replay.configure(text="▶ PLAY", fg_color="#1F6FEB")
    else:
        badge_replay.configure(text="PLAY", fg_color="#3A3A3A")

    app.after(120, update_badges)


# =========================================================
#  キー正規化（Hotkey文字列 <-> token set）
# =========================================================
MOD_TOKENS = {"ctrl", "alt", "shift", "win"}
VALID_F = {f"f{i}" for i in range(1, 25)}


def normalize_token(s: str) -> str:
    s = s.strip().lower()
    aliases = {
        "control": "ctrl",
        "ctl": "ctrl",
        "option": "alt",
        "windows": "win",
        "meta": "win",
        "cmd": "win",
        "escape": "esc",
        "return": "enter",
    }
    return aliases.get(s, s)


def parse_hotkey_string(hk: str) -> set:
    parts = [normalize_token(p) for p in hk.split("+") if p.strip()]
    tokens = set(parts)

    for t in tokens:
        if t in MOD_TOKENS:
            continue
        if t in VALID_F:
            continue
        if t in {"esc", "enter", "space", "tab", "backspace", "delete", "insert",
                 "home", "end", "pageup", "pagedown", "up", "down", "left", "right"}:
            continue
        if len(t) == 1 and (t.isalnum() or t in "-="):
            continue
        raise ValueError(f"不明なキー: {t}")

    non_mod = [t for t in tokens if t not in MOD_TOKENS]
    if len(non_mod) == 0:
        raise ValueError("修飾キーだけは不可です（例: Ctrl+Alt+1）")
    if len(non_mod) >= 2:
        raise ValueError("非修飾キーは1つにしてください（例: Ctrl+Alt+1 / F1）")

    return tokens


def tokens_to_string(tokens: set) -> str:
    order = ["ctrl", "alt", "shift", "win"]
    mods = [t for t in order if t in tokens]
    rest = [t for t in tokens if t not in MOD_TOKENS]
    key = rest[0] if rest else ""

    if key.startswith("f") and key[1:].isdigit():
        key_disp = key.upper()
    else:
        key_disp = key.upper() if len(key) == 1 else key.capitalize()

    out = [m.capitalize() if m != "ctrl" else "Ctrl" for m in mods]
    if key_disp:
        out.append(key_disp)
    return "+".join(out)


# =========================================================
#  pynput Key -> token
# =========================================================
def key_to_token(key) -> str | None:
    if isinstance(key, keyboard.KeyCode):
        if key.char:
            c = key.char.lower()
            if len(c) == 1:
                return c
        return None

    mapping = {
        keyboard.Key.ctrl_l: "ctrl",
        keyboard.Key.ctrl_r: "ctrl",
        keyboard.Key.alt_l: "alt",
        keyboard.Key.alt_r: "alt",
        keyboard.Key.shift: "shift",
        keyboard.Key.shift_l: "shift",
        keyboard.Key.shift_r: "shift",
        keyboard.Key.cmd: "win",
        keyboard.Key.cmd_l: "win",
        keyboard.Key.cmd_r: "win",
        keyboard.Key.esc: "esc",
        keyboard.Key.enter: "enter",
        keyboard.Key.space: "space",
        keyboard.Key.tab: "tab",
        keyboard.Key.backspace: "backspace",
        keyboard.Key.delete: "delete",
        keyboard.Key.insert: "insert",
        keyboard.Key.home: "home",
        keyboard.Key.end: "end",
        keyboard.Key.page_up: "pageup",
        keyboard.Key.page_down: "pagedown",
        keyboard.Key.up: "up",
        keyboard.Key.down: "down",
        keyboard.Key.left: "left",
        keyboard.Key.right: "right",
    }
    if key in mapping:
        return mapping[key]

    for i in range(1, 25):
        fkey = getattr(keyboard.Key, f"f{i}", None)
        if fkey is not None and key == fkey:
            return f"f{i}"

    return None


def rebuild_hotkey_sets():
    global hotkey_sets
    hotkey_sets = {}
    for action, hk_str in hotkeys.items():
        try:
            hotkey_sets[action] = parse_hotkey_string(hk_str)
        except Exception as e:
            append_log(f"[WARN] Hotkey parse failed: {action}={hk_str} ({e})")
            hotkey_sets[action] = set()


def hotkey_matches(action: str) -> bool:
    need = hotkey_sets.get(action) or set()
    # 完全一致（誤爆防止）
    return bool(need) and pressed_tokens == need


# =========================================================
#  マクロ保存/読み込み
# =========================================================
def sanitize_macro_name(name: str) -> str:
    name = name.strip()
    if not name:
        return "macro"
    safe = "".join(c for c in name if c.isalnum() or c in "._- ")
    safe = safe.strip()
    return safe[:80] if safe else "macro"


def get_macro_path(name: str) -> str:
    safe_name = sanitize_macro_name(name)
    return os.path.join(get_macros_folder(), f"{safe_name}.json")


def list_macros() -> list:
    folder = get_macros_folder()
    files = [f[:-5] for f in os.listdir(folder) if f.endswith(".json")]
    return sorted(files, key=lambda s: s.lower())


def ensure_macro_exists(name: str):
    path = get_macro_path(name)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"clicks": []}, f, ensure_ascii=False, indent=2)


def save_current_macro():
    global current_macro_name
    path = get_macro_path(current_macro_name)
    try:
        with lock:
            data = {"clicks": recorded_clicks}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        append_log(f"[INFO] マクロ保存: {current_macro_name} ({len(recorded_clicks)}クリック)")
    except Exception as e:
        append_log(f"[ERROR] マクロ保存失敗: {e}")


def load_macro(name: str):
    global current_macro_name, recorded_clicks, selected_macro_name
    path = get_macro_path(name)
    if not os.path.exists(path):
        append_log(f"[WARN] マクロが見つかりません: {name}")
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        with lock:
            recorded_clicks = data.get("clicks", [])
            current_macro_name = name
            selected_macro_name = name
        update_macro_label()
        append_log(f"[INFO] マクロ読み込み: {name} ({len(recorded_clicks)}クリック)")
        refresh_macro_list(select_name=name)
        save_config()
    except Exception as e:
        append_log(f"[ERROR] マクロ読み込み失敗: {e}")


def delete_macro(name: str):
    path = get_macro_path(name)
    try:
        if os.path.exists(path):
            os.remove(path)
            append_log(f"[INFO] マクロ削除: {name}")
        else:
            append_log(f"[WARN] マクロが存在しません: {name}")
    except Exception as e:
        append_log(f"[ERROR] マクロ削除失敗: {e}")


def rename_macro(old_name: str, new_name: str):
    global current_macro_name, selected_macro_name
    new_name = sanitize_macro_name(new_name)
    if not new_name or new_name == old_name:
        return

    old_path = get_macro_path(old_name)
    new_path = get_macro_path(new_name)

    try:
        if os.path.exists(new_path):
            append_log(f"[WARN] 同名が存在します: {new_name}")
            return
        if not os.path.exists(old_path):
            append_log(f"[WARN] 元が存在しません: {old_name}")
            return

        os.rename(old_path, new_path)

        if current_macro_name == old_name:
            current_macro_name = new_name
            update_macro_label()
        if selected_macro_name == old_name:
            selected_macro_name = new_name

        append_log(f"[INFO] マクロ名変更: {old_name} → {new_name}")
        refresh_macro_list(select_name=new_name)
        save_config()
    except Exception as e:
        append_log(f"[ERROR] マクロ名変更失敗: {e}")


# =========================================================
#  マウス録画
# =========================================================
def on_click(x, y, button, pressed):
    global last_click_time
    if not (recording and pressed):
        return

    now = time.time()
    with lock:
        elapsed = 0.0 if last_click_time is None else now - last_click_time
        last_click_time = now
        recorded_clicks.append((elapsed, x, y))

    append_log(f"[RECORD] ({x}, {y}) interval={elapsed:.2f}s")


# =========================================================
#  操作
# =========================================================
def start_recording():
    global recording, replaying, last_click_time
    with lock:
        if recording:
            append_log("[INFO] すでに録画中です。")
            return
        if replaying:
            append_log("[INFO] 再生中は録画開始できません。")
            return
        recorded_clicks.clear()
        last_click_time = None
        recording = True
    append_log(f"[INFO] 録画開始（マクロ: {current_macro_name}）")


def stop_recording():
    global recording
    with lock:
        if not recording:
            append_log("[INFO] 録画は開始されていません。")
            return
        recording = False
        count = len(recorded_clicks)
    append_log(f"[INFO] 録画停止。件数={count}")
    save_current_macro()
    refresh_macro_list(select_name=current_macro_name)


def start_replay():
    global replaying, recording

    with lock:
        if recording:
            append_log("[INFO] 録画中は再生できません。")
            return
        if replaying:
            append_log("[INFO] すでに再生中です。")
            return
        if not recorded_clicks:
            append_log("[INFO] 記録がありません。")
            return

        replaying = True
        seq = list(recorded_clicks)

    stop_event.clear()
    try:
        loops = int(loop_var.get())
        if loops <= 0:
            loops = 1
    except Exception:
        loops = 1

    threading.Thread(target=replay_worker, args=(seq, loops), daemon=True).start()


def force_stop():
    """統合版：録画も再生も全部止める（F4）"""
    global recording, replaying
    stop_event.set()

    with lock:
        was_recording = recording
        was_replaying = replaying
        recording = False
        replaying = False

    if was_recording:
        append_log("[FORCE STOP] 録画を強制停止しました")
    if was_replaying:
        append_log("[FORCE STOP] 再生を強制停止しました")
    if (not was_recording) and (not was_replaying):
        append_log("[INFO] 停止する処理がありませんでした")


def replay_worker(seq, loops: int):
    global replaying
    append_log(f"[INFO] 再生開始（{loops}回, マクロ: {current_macro_name}）")

    stopped = False
    try:
        for loop_i in range(1, loops + 1):
            if stop_event.is_set():
                stopped = True
                break

            append_log(f"== LOOP {loop_i}/{loops} ==")
            for i, (elapsed, x, y) in enumerate(seq):
                if stop_event.is_set():
                    stopped = True
                    break

                time.sleep(float(elapsed))

                if stop_event.is_set():
                    stopped = True
                    break

                pyautogui.moveTo(x, y)
                pyautogui.click()
                append_log(f"[REPLAY] loop={loop_i} step={i+1}/{len(seq)} ({x},{y}) +{float(elapsed):.2f}s")

            if stopped:
                break

    except pyautogui.FailSafeException:
        append_log("[FORCE STOP] pyautogui FAILSAFE 発動（マウスが画面端に移動）")
        stopped = True
    except Exception as e:
        append_log(f"[ERROR] 再生中に例外: {e}")
        stopped = True

    append_log("[INFO] 再生を停止しました。" if stopped else "[INFO] 再生完了。")

    with lock:
        replaying = False


def safe_quit():
    global mouse_listener, keyboard_listener
    stop_event.set()
    try:
        save_config()
    except Exception:
        pass
    try:
        if mouse_listener:
            mouse_listener.stop()
    except Exception:
        pass
    try:
        if keyboard_listener:
            keyboard_listener.stop()
    except Exception:
        pass
    try:
        app.destroy()
    except Exception:
        pass


# =========================================================
#  設定ロード/保存
# =========================================================
def load_config():
    global hotkeys, current_macro_name, selected_macro_name
    path = get_config_path()
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        lc = data.get("loop_count", DEFAULTS["loop_count"])
        try:
            loop_var.set(int(lc))
        except Exception:
            loop_var.set(DEFAULTS["loop_count"])

        hk = data.get("hotkeys", {})
        for k in DEFAULT_HOTKEYS.keys():
            v = hk.get(k)
            if isinstance(v, str) and v.strip():
                hotkeys[k] = v.strip()

        current_macro_name = data.get("current_macro", DEFAULTS["current_macro"])
        selected_macro_name = current_macro_name

        rebuild_hotkey_sets()
        update_macro_label()

        append_log(f"[INFO] 設定ロード: {path}")
    except Exception as e:
        append_log(f"[WARN] 設定ロード失敗: {e}")


def save_config():
    path = get_config_path()
    try:
        data = {
            "loop_count": int(loop_var.get()),
            "hotkeys": hotkeys,
            "current_macro": current_macro_name
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        append_log(f"[INFO] 設定保存: {path}")
    except Exception as e:
        append_log(f"[ERROR] 設定保存失敗: {e}")


# =========================================================
#  ホットキー変更（GUI）
# =========================================================
def refresh_hotkey_entries():
    for action, ent in entries.items():
        ent.delete(0, "end")
        ent.insert(0, hotkeys[action])


def apply_hotkey_from_entry(action: str, entry_widget):
    text = entry_widget.get().strip()
    if not text:
        append_log("[WARN] 空は不可")
        return
    try:
        tokens = parse_hotkey_string(text)
        hotkeys[action] = tokens_to_string(tokens)
        rebuild_hotkey_sets()
        refresh_hotkey_entries()
        append_log(f"[INFO] Hotkey更新: {action} = {hotkeys[action]}")
        save_config()
    except Exception as e:
        append_log(f"[WARN] Hotkey不正: {e}")


# =========================================================
#  キーボードフック（ブロック無し）
# =========================================================
def on_key_press(key):
    tok = key_to_token(key)
    if tok is None:
        return

    pressed_tokens.add(tok)

    if hotkey_matches("record_start"):
        start_recording()
    elif hotkey_matches("record_stop"):
        stop_recording()
    elif hotkey_matches("replay_start"):
        start_replay()
    elif hotkey_matches("force_stop"):
        force_stop()
    elif hotkey_matches("quit"):
        append_log("[INFO] Hotkey quit")
        safe_quit()


def on_key_release(key):
    tok = key_to_token(key)
    if tok is None:
        return
    pressed_tokens.discard(tok)


# =========================================================
#  マクロリスト更新（選択復元あり）
# =========================================================
def refresh_macro_list(select_name: str | None = None):
    global selected_macro_name

    if macro_listbox is None:
        return

    macro_listbox.delete(0, "end")
    macros = list_macros()

    if not macros:
        ensure_macro_exists("default")
        macros = list_macros()

    for m in macros:
        macro_listbox.insert("end", m)

    target = select_name or selected_macro_name or current_macro_name
    if target in macros:
        idx = macros.index(target)
        macro_listbox.selection_clear(0, "end")
        macro_listbox.selection_set(idx)
        macro_listbox.activate(idx)
        macro_listbox.see(idx)
        selected_macro_name = target


def update_macro_label():
    if current_macro_label is not None:
        current_macro_label.configure(text=f"現在: {current_macro_name}")


def get_selected_macro_name() -> str | None:
    if selected_macro_name:
        return selected_macro_name
    if macro_listbox is None:
        return None
    sel = macro_listbox.curselection()
    if not sel:
        return None
    return macro_listbox.get(sel[0])


# =========================================================
#  マクロ管理GUI操作
# =========================================================
def on_macro_select(event=None):
    global selected_macro_name
    if macro_listbox is None:
        return
    sel = macro_listbox.curselection()
    if not sel:
        return
    name = macro_listbox.get(sel[0])
    selected_macro_name = name
    load_macro(name)


def new_macro():
    global current_macro_name, recorded_clicks, selected_macro_name

    name = simpledialog.askstring("新規マクロ", "マクロ名を入力してください:", parent=app)
    if not name:
        return
    name = sanitize_macro_name(name)

    path = get_macro_path(name)
    if os.path.exists(path):
        messagebox.showwarning("注意", "同名のマクロが既に存在します。", parent=app)
        return

    with lock:
        current_macro_name = name
        selected_macro_name = name
        recorded_clicks = []

    save_current_macro()
    update_macro_label()
    refresh_macro_list(select_name=name)
    save_config()
    append_log(f"[INFO] 新規マクロ作成: {name}")


def delete_selected_macro():
    global current_macro_name, selected_macro_name

    name = get_selected_macro_name()
    if not name:
        append_log("[WARN] マクロが選択されていません")
        return

    if name.lower() == "default":
        messagebox.showwarning("注意", "default は削除できません。", parent=app)
        return

    if messagebox.askyesno("削除確認", f"マクロ '{name}' を削除しますか?", parent=app):
        delete_macro(name)

        if current_macro_name == name:
            current_macro_name = "default"
            ensure_macro_exists(current_macro_name)
            load_macro(current_macro_name)
        selected_macro_name = current_macro_name

        refresh_macro_list(select_name=current_macro_name)
        save_config()


def rename_selected_macro():
    global selected_macro_name

    old_name = get_selected_macro_name()
    if not old_name:
        append_log("[WARN] マクロが選択されていません")
        return
    if old_name.lower() == "default":
        messagebox.showwarning("注意", "default は名前変更できません。", parent=app)
        return

    new_name = simpledialog.askstring("名前変更", f"'{old_name}' の新しい名前:",
                                      initialvalue=old_name, parent=app)
    if not new_name:
        return

    rename_macro(old_name, new_name)
    refresh_macro_list(select_name=selected_macro_name or current_macro_name)


# =========================================================
#  UI
# =========================================================
ACTION_LABELS = {
    "record_start": "録画開始",
    "record_stop":  "録画停止",
    "replay_start": "再生開始",
    "force_stop":   "強制停止（全停止）",
    "quit":         "終了",
}


def build_ui():
    global app, log_box, loop_var, badge_record, badge_replay
    global macro_listbox, current_macro_label

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    app = ctk.CTk()
    app.title("Mouse Macro - Hotkey Priority (No Block)")
    app.geometry("1280x820")
    app.minsize(980, 650)

    app.grid_columnconfigure(0, weight=0)
    app.grid_columnconfigure(1, weight=1)
    app.grid_columnconfigure(2, weight=0)
    app.grid_rowconfigure(0, weight=1)

    # 左
    left = ctk.CTkFrame(app, corner_radius=16, width=430)
    left.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    left.grid_propagate(False)
    left.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(left, text="Mouse Macro", font=ctk.CTkFont(size=22, weight="bold")).grid(
        row=0, column=0, sticky="w", padx=16, pady=(16, 6)
    )

    current_macro_label = ctk.CTkLabel(left, text=f"現在: {current_macro_name}",
                                       font=ctk.CTkFont(size=12), text_color="#888")
    current_macro_label.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

    badge_row = ctk.CTkFrame(left, corner_radius=12)
    badge_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
    badge_row.grid_columnconfigure((0, 1), weight=1)

    badge_record = ctk.CTkLabel(badge_row, text="REC", corner_radius=10, fg_color="#3A3A3A",
                                font=ctk.CTkFont(size=14, weight="bold"))
    badge_record.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

    badge_replay = ctk.CTkLabel(badge_row, text="PLAY", corner_radius=10, fg_color="#3A3A3A",
                                font=ctk.CTkFont(size=14, weight="bold"))
    badge_replay.grid(row=0, column=1, sticky="ew", padx=10, pady=10)

    loop_box = ctk.CTkFrame(left, corner_radius=12)
    loop_box.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 10))
    loop_box.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(loop_box, text="ループ回数", font=ctk.CTkFont(size=14, weight="bold")).grid(
        row=0, column=0, padx=12, pady=12, sticky="w"
    )
    loop_var = tk.IntVar(master=app, value=1)
    ctk.CTkEntry(loop_box, textvariable=loop_var, justify="center", width=110).grid(
        row=0, column=1, padx=12, pady=12, sticky="e"
    )

    ctk.CTkButton(left, text="録画開始 (F1)", height=42, command=start_recording).grid(
        row=4, column=0, padx=16, pady=(0, 8), sticky="ew"
    )
    ctk.CTkButton(left, text="録画停止 (F2)", height=42, command=stop_recording).grid(
        row=5, column=0, padx=16, pady=(0, 8), sticky="ew"
    )
    ctk.CTkButton(left, text="再生開始 (F3)", height=42, command=start_replay).grid(
        row=6, column=0, padx=16, pady=(0, 8), sticky="ew"
    )
    ctk.CTkButton(left, text="強制停止 (F4)", height=42,
                  fg_color="#C0392B", hover_color="#E74C3C",
                  command=force_stop).grid(
        row=7, column=0, padx=16, pady=(0, 8), sticky="ew"
    )

    bottom_btns = ctk.CTkFrame(left, corner_radius=12)
    bottom_btns.grid(row=8, column=0, sticky="ew", padx=16, pady=(8, 8))
    bottom_btns.grid_columnconfigure((0, 1), weight=1)

    ctk.CTkButton(bottom_btns, text="設定保存", height=36, fg_color="#444", hover_color="#666",
                  command=save_config).grid(row=0, column=0, padx=6, pady=8, sticky="ew")
    ctk.CTkButton(bottom_btns, text="終了 (Esc)", height=36, fg_color="#444", hover_color="#666",
                  command=safe_quit).grid(row=0, column=1, padx=6, pady=8, sticky="ew")

    hk_container = ctk.CTkFrame(left, corner_radius=16)
    hk_container.grid(row=9, column=0, sticky="nsew", padx=16, pady=(0, 16))
    hk_container.grid_rowconfigure(1, weight=1)
    hk_container.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(hk_container, text="Hotkeys（直接入力→Enter/適用）",
                 font=ctk.CTkFont(size=14, weight="bold")).grid(
        row=0, column=0, sticky="w", padx=12, pady=(12, 6)
    )

    hk_scroll = ctk.CTkScrollableFrame(hk_container, corner_radius=12)
    hk_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
    hk_scroll.grid_columnconfigure(0, weight=0)
    hk_scroll.grid_columnconfigure(1, weight=1)
    hk_scroll.grid_columnconfigure(2, weight=0)

    row = 0
    for action in ["record_start", "record_stop", "replay_start", "force_stop", "quit"]:
        ctk.CTkLabel(hk_scroll, text=ACTION_LABELS[action]).grid(
            row=row, column=0, padx=8, pady=6, sticky="w"
        )

        ent = ctk.CTkEntry(hk_scroll)
        ent.grid(row=row, column=1, padx=8, pady=6, sticky="ew")
        entries[action] = ent

        ent.bind("<Return>", lambda e, a=action, w=ent: apply_hotkey_from_entry(a, w))

        ctk.CTkButton(
            hk_scroll, text="適用", width=58, height=28,
            command=lambda a=action, e=ent: apply_hotkey_from_entry(a, e)
        ).grid(row=row, column=2, padx=(0, 8), pady=6, sticky="e")

        row += 1

    left.grid_rowconfigure(9, weight=1)

    # 中央ログ
    center = ctk.CTkFrame(app, corner_radius=16)
    center.grid(row=0, column=1, sticky="nsew", padx=(0, 8), pady=16)
    center.grid_rowconfigure(1, weight=1)
    center.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(center, text="Log", font=ctk.CTkFont(size=18, weight="bold")).grid(
        row=0, column=0, sticky="w", padx=16, pady=(16, 8)
    )

    log_box = ctk.CTkTextbox(center, corner_radius=12, wrap="word")
    log_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
    log_box.configure(state="disabled")

    # 右マクロ管理
    right = ctk.CTkFrame(app, corner_radius=16, width=300)
    right.grid(row=0, column=2, sticky="nsew", padx=(0, 16), pady=16)
    right.grid_propagate(False)
    right.grid_rowconfigure(2, weight=1)
    right.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(right, text="マクロ管理", font=ctk.CTkFont(size=18, weight="bold")).grid(
        row=0, column=0, sticky="w", padx=16, pady=(16, 8)
    )

    btn_frame = ctk.CTkFrame(right, corner_radius=12)
    btn_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
    btn_frame.grid_columnconfigure((0, 1, 2), weight=1)

    ctk.CTkButton(btn_frame, text="新規", height=32, command=new_macro).grid(
        row=0, column=0, padx=4, pady=8, sticky="ew"
    )
    ctk.CTkButton(btn_frame, text="削除", height=32,
                  fg_color="#C0392B", hover_color="#E74C3C",
                  command=delete_selected_macro).grid(
        row=0, column=1, padx=4, pady=8, sticky="ew"
    )
    ctk.CTkButton(btn_frame, text="名前変更", height=32,
                  command=rename_selected_macro).grid(
        row=0, column=2, padx=4, pady=8, sticky="ew"
    )

    list_frame = ctk.CTkFrame(right, corner_radius=12)
    list_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 16))
    list_frame.grid_rowconfigure(0, weight=1)
    list_frame.grid_columnconfigure(0, weight=1)

    macro_listbox = tk.Listbox(
        list_frame,
        bg="#2B2B2B", fg="#FFFFFF",
        selectbackground="#1F6FEB", selectforeground="#FFFFFF",
        font=("Segoe UI", 11),
        relief="flat", borderwidth=0,
        exportselection=False
    )
    macro_listbox.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
    macro_listbox.bind("<<ListboxSelect>>", on_macro_select)

    scrollbar = ctk.CTkScrollbar(list_frame, command=macro_listbox.yview)
    scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
    macro_listbox.configure(yscrollcommand=scrollbar.set)

    refresh_hotkey_entries()
    refresh_macro_list(select_name=current_macro_name)

    append_log("[INFO] 起動しました（ブロック無し / Hotkey最優先）")
    append_log("[INFO] もしF1が効かないなら、別アプリが奪ってる or Fn絡みの可能性あり")

    update_badges()


# =========================================================
#  メイン
# =========================================================
def main():
    global mouse_listener, keyboard_listener

    rebuild_hotkey_sets()
    build_ui()

    load_config()
    refresh_hotkey_entries()

    ensure_macro_exists(current_macro_name)
    refresh_macro_list(select_name=current_macro_name)
    load_macro(current_macro_name)

    mouse_listener = mouse.Listener(on_click=on_click)
    mouse_listener.start()

    keyboard_listener = keyboard.Listener(on_press=on_key_press, on_release=on_key_release)
    keyboard_listener.start()

    app.protocol("WM_DELETE_WINDOW", safe_quit)
    app.mainloop()


if __name__ == "__main__":
    main()
    append_log(f"[DEBUG] APPDATA={os.environ.get('APPDATA')}")
    append_log(f"[DEBUG] HOME={os.path.expanduser('~')}")
    append_log(f"[DEBUG] config_path={get_config_path()}")
    append_log(f"[DEBUG] macros_folder={get_macros_folder()}")