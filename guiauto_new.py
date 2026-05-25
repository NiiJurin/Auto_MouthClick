import os
import json
import time
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import simpledialog, messagebox

import customtkinter as ctk
import pyautogui
from pynput import mouse, keyboard

try:
    import pyperclip
except Exception:
    pyperclip = None


# =========================================================
#  設定（保存先）
# =========================================================
APP_NAME = "MouseMacroCTK"
APP_VERSION = "0.9.0"
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
    "combo_outer_loop_count": 1,
    "combo_plan": [],
    "play_mode": "single",
    "appearance_mode": "light",
    "hotkeys": dict(DEFAULT_HOTKEYS),
    "current_macro": "default"
}


UI_FONT_FAMILY = "Yu Gothic UI"

UI_PALETTES = {
    "light": {
        "bg": "#EEF1F5",
        "panel": "#FFFFFF",
        "panel_2": "#F8FAFC",
        "surface": "#FBFCFE",
        "line": "#D9DEE7",
        "line_strong": "#BCC5D3",
        "text": "#1C2430",
        "muted": "#697386",
        "blue": "#2474B8",
        "blue_hover": "#155F9D",
        "red": "#CF3A30",
        "red_hover": "#B8322A",
        "subtle": "#E6EBF2",
        "subtle_hover": "#D8E0EA",
        "list_bg": "#FFFFFF",
        "list_selected": "#E9F2FB",
        "combo_selected": "#EAF4FF",
        "log_bg": "#111827",
        "log_text": "#E5E7EB",
        "warning_text": "#A96F16",
        "success_text": "#23885F",
        "focus": "#9CC6EA",
    },
    "dark": {
        "bg": "#111112",
        "panel": "#1B1B1D",
        "panel_2": "#242426",
        "surface": "#181819",
        "line": "#343437",
        "line_strong": "#55565A",
        "text": "#F3F4F6",
        "muted": "#A8ABB3",
        "blue": "#2474B8",
        "blue_hover": "#155F9D",
        "red": "#CF3A30",
        "red_hover": "#B8322A",
        "subtle": "#2D2D31",
        "subtle_hover": "#3A3A3F",
        "list_bg": "#161618",
        "list_selected": "#233A50",
        "combo_selected": "#243A4C",
        "log_bg": "#101114",
        "log_text": "#E5E7EB",
        "warning_text": "#F0B35A",
        "success_text": "#57C785",
        "focus": "#6AA5D7",
    },
}


def normalize_appearance_mode(value) -> str:
    text = str(value or "").strip().lower()
    if text in {"dark", "ダーク", "暗"}:
        return "dark"
    return "light"


def ctk_appearance_name(mode: str | None = None) -> str:
    return "Dark" if normalize_appearance_mode(mode or appearance_mode) == "dark" else "Light"


def appearance_mode_to_label(mode: str) -> str:
    return "ダーク" if normalize_appearance_mode(mode) == "dark" else "ライト"


def appearance_mode_from_label(label: str) -> str:
    return "dark" if label == "ダーク" else "light"


def theme_pair(key: str):
    return (UI_PALETTES["light"][key], UI_PALETTES["dark"][key])


def theme_color(key: str, mode: str | None = None) -> str:
    mode = normalize_appearance_mode(mode or appearance_mode)
    return UI_PALETTES[mode][key]


def read_saved_appearance_mode() -> str:
    path = get_config_path()
    if not os.path.exists(path):
        return DEFAULTS["appearance_mode"]
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return normalize_appearance_mode(data.get("appearance_mode", DEFAULTS["appearance_mode"]))
    except Exception:
        return DEFAULTS["appearance_mode"]


def configure_default_fonts(root=None):
    try:
        ctk.ThemeManager.theme["CTkFont"]["family"] = UI_FONT_FAMILY
    except Exception:
        pass
    if root is not None:
        try:
            root.option_add("*Font", f"{{{UI_FONT_FAMILY}}} 10")
        except Exception:
            pass
    for font_name in (
        "TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
        "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont",
    ):
        try:
            tkfont.nametofont(font_name).configure(family=UI_FONT_FAMILY)
        except Exception:
            pass


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
replay_run_id = 0

mouse_listener = None
keyboard_listener = None

app = None
log_box = None
log_panel = None
log_body_frame = None
log_toggle_button = None
log_status_label = None
log_clear_button = None
log_expanded = False
loop_var = None
play_mode_var = None
appearance_mode = DEFAULTS["appearance_mode"]
appearance_mode_var = None
play_mode_status_label = None
playlist_state_label = None
playlist_toggle_button = None
main_workspace = None
playlist_panel = None
dashboard_macro_label = None
dashboard_mode_label = None
dashboard_plan_label = None
dashboard_status_label = None
dashboard_status_strip = None
last_status_message = "起動準備中"
last_status_kind = "info"

badge_record = None
badge_replay = None

macro_listbox = None
current_macro_label = None
macro_list_names = []
combo_listbox = None
combo_steps_frame = None
combo_outer_loop_var = None
combo_summary_label = None
combo_plan = []
selected_combo_index = None
combo_move_job = None
combo_drag_index = None
click_capture_callback = None

# Hotkey
hotkeys = dict(DEFAULT_HOTKEYS)   # action -> "F1" 等
hotkey_sets = {}                 # action -> set(tokens)
pressed_tokens = set()           # 現在押されてる token
hotkey_last_trigger = {}
HOTKEY_COOLDOWN_SECONDS = 0.35

entries = {}  # action -> CTkEntry widget


# =========================================================
#  ログ（GUIスレッド安全）
# =========================================================
LOG_KIND_COLORS = {
    "info": "#B8C0CC",
    "success": "#57C785",
    "warning": "#F0B35A",
    "error": "#F06767",
}


def compact_status_message(msg: str, limit: int = 96) -> str:
    text = " ".join(str(msg).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def dashboard_status_message(msg: str) -> str:
    text = compact_status_message(msg, 72)
    if len(text) < 28:
        return text
    for marker in [" (", " / ", " → "]:
        if marker in text:
            return text.replace(marker, "\n" + marker.lstrip(), 1)
    return text


def classify_log_kind(msg: str) -> str:
    text = str(msg)
    if any(word in text for word in ["エラー", "失敗", "不正"]):
        return "error"
    if any(word in text for word in ["停止", "ありません", "できません", "空です", "見つかりません", "同名"]):
        return "warning"
    if any(word in text for word in ["完了", "保存", "追加", "複製", "選択", "新規", "更新", "起動"]):
        return "success"
    return "info"


def update_status_surfaces(msg: str, kind: str):
    short_msg = compact_status_message(msg)
    color = LOG_KIND_COLORS.get(kind, LOG_KIND_COLORS["info"])
    if log_status_label is not None:
        log_status_label.configure(text=short_msg, text_color=color)
    if dashboard_status_label is not None:
        dashboard_status_label.configure(text=dashboard_status_message(msg), text_color=color)
    if dashboard_status_strip is not None:
        dashboard_status_strip.configure(fg_color=color)


def append_log(msg: str):
    global last_status_message, last_status_kind
    last_status_message = str(msg)
    last_status_kind = classify_log_kind(last_status_message)
    print(msg)
    if app is None or log_box is None:
        return

    def _write():
        log_box.configure(state="normal")
        log_box.insert("end", msg + "\n")
        log_box.see("end")
        log_box.configure(state="disabled")
        update_status_surfaces(last_status_message, last_status_kind)
        if last_status_kind == "error":
            set_log_expanded(True)

    app.after(0, _write)


def clear_log():
    global last_status_message, last_status_kind
    if log_box is None:
        return
    log_box.configure(state="normal")
    log_box.delete("1.0", "end")
    log_box.configure(state="disabled")
    last_status_message = "ログをクリアしました"
    last_status_kind = "info"
    update_status_surfaces(last_status_message, last_status_kind)


def set_log_expanded(expanded: bool):
    global log_expanded
    log_expanded = expanded
    if log_body_frame is None or log_toggle_button is None:
        return
    if expanded:
        log_body_frame.grid()
        log_toggle_button.configure(text="⌄")
    else:
        log_body_frame.grid_remove()
        log_toggle_button.configure(text="⌃")
    if log_clear_button is not None:
        log_clear_button.grid()


def toggle_log_panel():
    set_log_expanded(not log_expanded)


# =========================================================
#  状態バッジ更新
# =========================================================
def update_badges():
    if badge_record is None or badge_replay is None:
        return

    if recording:
        badge_record.configure(text="● REC", fg_color="#C0392B", text_color="#FFFFFF")
    else:
        badge_record.configure(text="REC", fg_color=theme_pair("subtle"), text_color=theme_pair("text"))

    if replaying:
        badge_replay.configure(text="▶ PLAY", fg_color="#1F6FEB", text_color="#FFFFFF")
    else:
        badge_replay.configure(text="PLAY", fg_color=theme_pair("subtle"), text_color=theme_pair("text"))

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
    return bool(need) and need.issubset(pressed_tokens)


def run_hotkey_action(action: str):
    if action == "record_start":
        start_recording()
    elif action == "record_stop":
        stop_recording()
    elif action == "replay_start":
        start_replay()
    elif action == "force_stop":
        force_stop()
    elif action == "quit":
        append_log("終了します")
        safe_quit()


def trigger_hotkey_if_needed() -> bool:
    for action in ["record_start", "record_stop", "replay_start", "force_stop", "quit"]:
        if not hotkey_matches(action):
            continue

        now = time.time()
        last = hotkey_last_trigger.get(action, 0)
        if now - last < HOTKEY_COOLDOWN_SECONDS:
            pressed_tokens.clear()
            return True

        hotkey_last_trigger[action] = now
        run_hotkey_action(action)

        # Key release events can occasionally be missed by the OS hook.
        # Resetting here keeps F1/F2/F3 from getting stuck as "already pressed".
        pressed_tokens.clear()
        return True
    return False


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


def read_macro_clicks(name: str) -> list:
    path = get_macro_path(name)
    if not os.path.exists(path):
        raise FileNotFoundError(name)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    clicks = data.get("clicks", [])
    if not isinstance(clicks, list):
        return []
    return clicks


def write_macro_clicks(name: str, clicks: list):
    path = get_macro_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"clicks": clicks}, f, ensure_ascii=False, indent=2)


def macro_duration_seconds(clicks: list) -> float:
    total = 0.0
    for click in clicks:
        try:
            total += max(0.0, float(click[0]))
        except Exception:
            pass
    return total


def get_macro_duration_seconds(name: str) -> float:
    try:
        return macro_duration_seconds(read_macro_clicks(name))
    except Exception:
        return 0.0


def format_duration(seconds: float) -> str:
    try:
        seconds = max(0.0, float(seconds))
    except Exception:
        seconds = 0.0
    return f"{seconds:.1f}秒"


def mouse_button_to_name(button) -> str:
    if button == mouse.Button.right:
        return "right"
    if button == mouse.Button.middle:
        return "middle"
    return "left"


def mouse_button_label(button_name: str) -> str:
    labels = {
        "left": "左",
        "right": "右",
        "middle": "中",
    }
    return labels.get(button_name, "左")


def button_label_to_name(label: str) -> str:
    names = {
        "左": "left",
        "右": "right",
        "中": "middle",
    }
    return names.get(label, "left")


def normalize_click(click):
    elapsed = click[0] if len(click) > 0 else 0.0
    x = click[1] if len(click) > 1 else 0
    y = click[2] if len(click) > 2 else 0
    button_name = click[3] if len(click) > 3 else "left"
    if button_name not in {"left", "right", "middle"}:
        button_name = "left"
    input_text = click[4] if len(click) > 4 else ""
    if input_text is None:
        input_text = ""
    return elapsed, x, y, button_name, str(input_text)


def paste_text_after_click(text: str):
    if not text:
        return
    if pyperclip is not None:
        try:
            old_text = pyperclip.paste()
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.05)
            pyperclip.copy(old_text)
            return
        except Exception:
            pass
    pyautogui.write(text, interval=0.01)


def normalize_loop_count(value, default: int = 1) -> int:
    try:
        count = int(value)
    except Exception:
        count = default
    return max(1, count)


def play_mode_to_label(mode: str) -> str:
    return "複数" if mode == "playlist" else "単体"


def play_mode_from_label(label: str) -> str:
    return "playlist" if label == "複数" else "single"


def get_play_mode() -> str:
    if play_mode_var is None:
        return DEFAULTS["play_mode"]
    return play_mode_from_label(play_mode_var.get())


def set_play_mode(mode: str):
    if play_mode_var is not None:
        play_mode_var.set(play_mode_to_label(mode))
    update_play_mode_status()
    update_combo_summary()


def toggle_playlist_mode():
    set_play_mode("single" if get_play_mode() == "playlist" else "playlist")
    save_config(silent=True)


def set_appearance_mode(mode: str, save: bool = True):
    global appearance_mode
    appearance_mode = normalize_appearance_mode(mode)
    ctk.set_appearance_mode(ctk_appearance_name(appearance_mode))
    if appearance_mode_var is not None:
        appearance_mode_var.set(appearance_mode_to_label(appearance_mode))
    apply_tk_widget_colors()
    if save:
        save_config(silent=True)


def set_appearance_mode_from_label(label: str):
    set_appearance_mode(appearance_mode_from_label(label), save=True)


def apply_tk_widget_colors():
    if macro_listbox is not None:
        macro_listbox.configure(
            bg=theme_color("list_bg"),
            fg=theme_color("text"),
            selectbackground=theme_color("list_selected"),
            selectforeground=theme_color("text"),
            highlightbackground=theme_color("line"),
            highlightcolor=theme_color("focus"),
        )


def sync_playlist_panel_visibility(mode: str | None = None):
    if main_workspace is None or playlist_panel is None:
        return

    if mode is None:
        mode = get_play_mode()

    if mode == "playlist":
        main_workspace.grid_columnconfigure(2, weight=0, minsize=370)
        playlist_panel.grid(row=0, column=2, sticky="nsew")
    else:
        playlist_panel.grid_remove()
        main_workspace.grid_columnconfigure(2, weight=0, minsize=0)


def update_play_mode_status():
    mode = get_play_mode()
    sync_playlist_panel_visibility(mode)
    if mode == "playlist":
        count = len(combo_plan)
        if play_mode_status_label is not None:
            play_mode_status_label.configure(
                text=f"F3: 複数 ON ({count}ステップ)",
                text_color=theme_pair("text") if count else theme_pair("warning_text"),
            )
        if playlist_state_label is not None:
            playlist_state_label.configure(text="ON: F3は複数", text_color=theme_pair("success_text"))
        if playlist_toggle_button is not None:
            playlist_toggle_button.configure(text="複数をOFF")
    else:
        if play_mode_status_label is not None:
            play_mode_status_label.configure(
                text=f"F3: 単体 ({current_macro_name})",
                text_color=theme_pair("text"),
            )
        if playlist_state_label is not None:
            playlist_state_label.configure(text="OFF: F3は単体", text_color=theme_pair("muted"))
        if playlist_toggle_button is not None:
            playlist_toggle_button.configure(text="複数をON")
    update_dashboard()


def update_dashboard():
    if dashboard_macro_label is None:
        return

    try:
        clicks = list(recorded_clicks) if current_macro_name == selected_macro_name else read_macro_clicks(current_macro_name)
    except Exception:
        clicks = []
    macro_seconds = macro_duration_seconds(clicks)
    dashboard_macro_label.configure(
        text=f"{current_macro_name}\n{len(clicks)}クリック / {format_duration(macro_seconds)}"
    )

    mode = get_play_mode()
    if mode == "playlist":
        mode_text = f"複数\n{len(combo_plan)}ステップ"
    else:
        single_loops = normalize_loop_count(loop_var.get() if loop_var else 1)
        mode_text = f"単体\n{single_loops}回"
    dashboard_mode_label.configure(text=mode_text)

    one_round = 0.0
    for item in combo_plan:
        one_round += get_macro_duration_seconds(item["name"]) * normalize_loop_count(item.get("loops", 1))
    outer = normalize_loop_count(combo_outer_loop_var.get() if combo_outer_loop_var else 1)
    dashboard_plan_label.configure(
        text=f"1周 {format_duration(one_round)}\n全体 {format_duration(one_round * outer)}"
    )

    update_status_surfaces(last_status_message, last_status_kind)


def save_current_macro():
    global current_macro_name
    path = get_macro_path(current_macro_name)
    try:
        with lock:
            data = {"clicks": recorded_clicks}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        update_macro_label()
        append_log(
            f"保存: {current_macro_name} "
            f"({len(recorded_clicks)}クリック / {format_duration(macro_duration_seconds(recorded_clicks))})"
        )
    except Exception as e:
        append_log(f"[ERROR] マクロ保存失敗: {e}")


def load_macro(name: str):
    global current_macro_name, recorded_clicks, selected_macro_name
    path = get_macro_path(name)
    if not os.path.exists(path):
        append_log(f"見つかりません: {name}")
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        with lock:
            recorded_clicks = data.get("clicks", [])
            current_macro_name = name
            selected_macro_name = name
        update_macro_label()
        append_log(
            f"選択: {name} "
            f"({len(recorded_clicks)}クリック / {format_duration(macro_duration_seconds(recorded_clicks))})"
        )
        refresh_macro_list(select_name=name)
        save_config(silent=True)
    except Exception as e:
        append_log(f"[ERROR] マクロ読み込み失敗: {e}")


def delete_macro(name: str):
    path = get_macro_path(name)
    try:
        if os.path.exists(path):
            os.remove(path)
            append_log(f"削除: {name}")
        else:
            append_log(f"存在しません: {name}")
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
            append_log(f"同名があります: {new_name}")
            return
        if not os.path.exists(old_path):
            append_log(f"見つかりません: {old_name}")
            return

        os.rename(old_path, new_path)

        if current_macro_name == old_name:
            current_macro_name = new_name
            update_macro_label()
        if selected_macro_name == old_name:
            selected_macro_name = new_name

        append_log(f"名前変更: {old_name} → {new_name}")
        refresh_macro_list(select_name=new_name)
        save_config(silent=True)
    except Exception as e:
        append_log(f"[ERROR] マクロ名変更失敗: {e}")


# =========================================================
#  マウス録画
# =========================================================
def set_click_capture(callback):
    global click_capture_callback
    click_capture_callback = callback


def clear_click_capture():
    global click_capture_callback
    click_capture_callback = None


def on_click(x, y, button, pressed):
    global last_click_time, click_capture_callback
    if pressed and click_capture_callback is not None:
        callback = click_capture_callback
        click_capture_callback = None
        button_name = mouse_button_to_name(button)
        if app is not None:
            app.after(0, lambda: callback(int(x), int(y), button_name))
        return

    if not (recording and pressed):
        return

    now = time.time()
    with lock:
        elapsed = 0.0 if last_click_time is None else now - last_click_time
        last_click_time = now
        button_name = mouse_button_to_name(button)
        recorded_clicks.append((elapsed, x, y, button_name, ""))

    append_log(f"録画中: {len(recorded_clicks)}クリック ({mouse_button_label(button_name)})")


# =========================================================
#  操作
# =========================================================
def start_recording():
    global recording, replaying, last_click_time
    with lock:
        if recording:
            append_log("すでに録画中です")
            return
        if replaying:
            append_log("再生中は録画できません")
            return
        recorded_clicks.clear()
        last_click_time = None
        recording = True
    append_log(f"録画開始: {current_macro_name}")


def stop_recording():
    global recording
    with lock:
        if not recording:
            append_log("録画は開始されていません")
            return
        recording = False
        count = len(recorded_clicks)
    append_log(f"録画停止: {count}クリック / {format_duration(macro_duration_seconds(recorded_clicks))}")
    save_current_macro()
    refresh_macro_list(select_name=current_macro_name)


def start_replay():
    global replaying, recording, replay_run_id

    with lock:
        if recording:
            append_log("録画中は再生できません")
            return
        if replaying:
            append_log("すでに再生中です")
            return

    stop_event.clear()
    try:
        if get_play_mode() == "playlist":
            if not combo_plan:
                append_log("複数リストが空です")
                return
            plan = build_combo_replay_plan()
            loops = normalize_loop_count(combo_outer_loop_var.get() if combo_outer_loop_var else 1)
        else:
            if not recorded_clicks:
                append_log("記録がありません")
                return
            plan = [{
                "name": current_macro_name,
                "loops": normalize_loop_count(loop_var.get() if loop_var else 1),
                "clicks": list(recorded_clicks),
                "duration": macro_duration_seconds(recorded_clicks),
            }]
            loops = 1
    except Exception as e:
        append_log(f"再生準備失敗: {e}")
        return

    with lock:
        replaying = True
        replay_run_id += 1
        run_id = replay_run_id

    threading.Thread(target=replay_worker, args=(plan, loops, run_id), daemon=True).start()


def start_click_test_replay(clicks: list, name: str):
    global replaying, replay_run_id
    if not clicks:
        append_log("テストするクリックがありません")
        return
    with lock:
        if recording:
            append_log("録画中はテスト再生できません")
            return
        if replaying:
            append_log("再生中はテスト再生できません")
            return
        replaying = True
        replay_run_id += 1
        run_id = replay_run_id

    normalized = [list(normalize_click(click)) for click in clicks]
    normalized[0][0] = 0.0
    stop_event.clear()
    plan = [{
        "name": name,
        "loops": 1,
        "clicks": normalized,
        "duration": macro_duration_seconds(normalized),
    }]
    threading.Thread(target=replay_worker, args=(plan, 1, run_id), daemon=True).start()


def force_stop():
    """統合版：録画も再生も全部止める（F4）"""
    global recording, replaying, replay_run_id
    stop_event.set()

    with lock:
        replay_run_id += 1
        was_recording = recording
        was_replaying = replaying
        recording = False
        replaying = False

    if was_recording:
        append_log("録画を停止しました")
    if was_replaying:
        append_log("再生を停止しました")
    if (not was_recording) and (not was_replaying):
        append_log("停止する処理がありません")


def replay_cancelled(run_id: int) -> bool:
    return stop_event.is_set() or run_id != replay_run_id


def wait_replay_delay(seconds: float, run_id: int) -> bool:
    try:
        seconds = max(0.0, float(seconds))
    except Exception:
        seconds = 0.0
    if replay_cancelled(run_id):
        return True
    if stop_event.wait(seconds):
        return True
    return replay_cancelled(run_id)


def replay_worker(plan: list, loops: int, run_id: int):
    global replaying
    total_seconds = sum(
        float(step.get("duration", macro_duration_seconds(step["clicks"]))) * int(step["loops"])
        for step in plan
    ) * loops
    append_log(f"再生開始: {len(plan)}ステップ / 予定 {format_duration(total_seconds)}")

    stopped = False
    try:
        for outer_i in range(1, loops + 1):
            if replay_cancelled(run_id):
                stopped = True
                break

            if loops > 1:
                append_log(f"全体ループ: {outer_i}/{loops}")
            for step_i, step in enumerate(plan, start=1):
                name = step["name"]
                seq = step["clicks"]
                step_loops = step["loops"]
                step_seconds = float(step.get("duration", macro_duration_seconds(seq))) * step_loops

                for loop_i in range(1, step_loops + 1):
                    if replay_cancelled(run_id):
                        stopped = True
                        break

                    for click in seq:
                        elapsed, x, y, button_name, input_text = normalize_click(click)
                        if replay_cancelled(run_id):
                            stopped = True
                            break

                        if wait_replay_delay(elapsed, run_id):
                            stopped = True
                            break

                        pyautogui.moveTo(x, y)
                        pyautogui.click(button=button_name)
                        paste_text_after_click(input_text)

                    if stopped:
                        break

                if not stopped:
                    append_log(
                        f"完了: {step_i}/{len(plan)} {name} x{step_loops} "
                        f"({format_duration(step_seconds)})"
                    )

                if replay_cancelled(run_id):
                    stopped = True
                    break

            if stopped:
                break

    except pyautogui.FailSafeException:
        append_log("停止: マウスが画面端に移動しました")
        stopped = True
    except Exception as e:
        append_log(f"再生エラー: {e}")
        stopped = True

    append_log("再生停止" if stopped else "再生完了")

    with lock:
        if run_id == replay_run_id:
            replaying = False


def safe_quit():
    global mouse_listener, keyboard_listener
    stop_event.set()
    clear_click_capture()
    try:
        save_config(silent=True)
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
    global hotkeys, current_macro_name, selected_macro_name, combo_plan
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

        combo_lc = data.get("combo_outer_loop_count", DEFAULTS["combo_outer_loop_count"])
        try:
            if combo_outer_loop_var is not None:
                combo_outer_loop_var.set(int(combo_lc))
        except Exception:
            if combo_outer_loop_var is not None:
                combo_outer_loop_var.set(DEFAULTS["combo_outer_loop_count"])

        raw_plan = data.get("combo_plan", DEFAULTS["combo_plan"])
        combo_plan = []
        if isinstance(raw_plan, list):
            for item in raw_plan:
                if not isinstance(item, dict):
                    continue
                name = sanitize_macro_name(str(item.get("name", "")))
                if not name:
                    continue
                combo_plan.append({
                    "name": name,
                    "loops": normalize_loop_count(item.get("loops", 1)),
                })

        hk = data.get("hotkeys", {})
        for k in DEFAULT_HOTKEYS.keys():
            v = hk.get(k)
            if isinstance(v, str) and v.strip():
                hotkeys[k] = v.strip()

        current_macro_name = data.get("current_macro", DEFAULTS["current_macro"])
        selected_macro_name = current_macro_name
        set_appearance_mode(data.get("appearance_mode", appearance_mode), save=False)
        set_play_mode(data.get("play_mode", DEFAULTS["play_mode"]))

        rebuild_hotkey_sets()
        update_macro_label()
        refresh_combo_list()

        append_log("設定を読み込みました")
    except Exception as e:
        append_log(f"設定ロード失敗: {e}")


def save_config(silent: bool = False):
    update_combo_summary()
    path = get_config_path()
    try:
        data = {
            "loop_count": normalize_loop_count(loop_var.get() if loop_var else 1),
            "combo_outer_loop_count": normalize_loop_count(
                combo_outer_loop_var.get() if combo_outer_loop_var else 1
            ),
            "combo_plan": [
                {"name": item["name"], "loops": normalize_loop_count(item.get("loops", 1))}
                for item in combo_plan
            ],
            "play_mode": get_play_mode(),
            "appearance_mode": appearance_mode,
            "hotkeys": hotkeys,
            "current_macro": current_macro_name
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if not silent:
            append_log("設定を保存しました")
    except Exception as e:
        append_log(f"設定保存失敗: {e}")


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
        append_log("Hotkeyが空です")
        return
    try:
        tokens = parse_hotkey_string(text)
        hotkeys[action] = tokens_to_string(tokens)
        rebuild_hotkey_sets()
        refresh_hotkey_entries()
        append_log(f"Hotkey更新: {ACTION_LABELS.get(action, action)} = {hotkeys[action]}")
        save_config(silent=True)
    except Exception as e:
        append_log(f"Hotkey不正: {e}")


# =========================================================
#  キーボードフック（ブロック無し）
# =========================================================
def on_key_press(key):
    try:
        tok = key_to_token(key)
        if tok is None:
            return

        pressed_tokens.add(tok)
        trigger_hotkey_if_needed()
    except Exception as e:
        pressed_tokens.clear()
        append_log(f"Hotkeyエラー: {e}")


def on_key_release(key):
    try:
        tok = key_to_token(key)
        if tok is None:
            return
        pressed_tokens.discard(tok)
    except Exception:
        pressed_tokens.clear()


# =========================================================
#  マクロリスト更新（選択復元あり）
# =========================================================
def refresh_macro_list(select_name: str | None = None):
    global selected_macro_name, macro_list_names

    if macro_listbox is None:
        return

    macro_listbox.delete(0, "end")
    macros = list_macros()

    if not macros:
        ensure_macro_exists("default")
        macros = list_macros()

    macro_list_names = macros
    for m in macros:
        try:
            clicks = read_macro_clicks(m)
        except Exception:
            clicks = []
        seconds = macro_duration_seconds(clicks)
        macro_listbox.insert("end", f"{m}  ({format_duration(seconds)} / {len(clicks)}クリック)")

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
        current_macro_label.configure(
            text=f"選択中: {current_macro_name} / {format_duration(get_macro_duration_seconds(current_macro_name))}"
        )
    update_play_mode_status()


def get_selected_macro_name() -> str | None:
    if macro_listbox is None:
        return selected_macro_name
    sel = macro_listbox.curselection()
    if sel and int(sel[0]) < len(macro_list_names):
        return macro_list_names[int(sel[0])]
    return selected_macro_name


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
    idx = int(sel[0])
    if idx >= len(macro_list_names):
        return
    name = macro_list_names[idx]
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
    save_config(silent=True)
    append_log(f"新規: {name}")


def delete_selected_macro():
    global current_macro_name, selected_macro_name

    name = get_selected_macro_name()
    if not name:
        append_log("マクロを選択してください")
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
        save_config(silent=True)


def rename_selected_macro():
    global selected_macro_name

    old_name = get_selected_macro_name()
    if not old_name:
        append_log("マクロを選択してください")
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


def duplicate_selected_macro():
    name = get_selected_macro_name()
    if not name:
        append_log("複製するマクロを選択してください")
        return

    default_name = sanitize_macro_name(f"{name}_copy")
    new_name = simpledialog.askstring("マクロ複製", "複製後の名前:", initialvalue=default_name, parent=app)
    if not new_name:
        return
    new_name = sanitize_macro_name(new_name)
    new_path = get_macro_path(new_name)
    if os.path.exists(new_path):
        messagebox.showwarning("注意", "同名のマクロが既に存在します。", parent=app)
        return

    try:
        with open(get_macro_path(name), "r", encoding="utf-8") as f:
            data = json.load(f)
        with open(new_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        refresh_macro_list(select_name=new_name)
        append_log(f"複製: {name} → {new_name}")
    except Exception as e:
        append_log(f"複製失敗: {e}")


# =========================================================
#  マクロ編集
# =========================================================
def open_macro_editor():
    name = get_selected_macro_name()
    if not name:
        append_log("編集するマクロを選択してください")
        return
    if recording or replaying:
        append_log("録画/再生中は編集できません")
        return

    try:
        clicks = [list(normalize_click(click)) for click in read_macro_clicks(name)]
    except Exception as e:
        append_log(f"編集開始失敗: {e}")
        return

    editor = ctk.CTkToplevel(app)
    editor.title(f"マクロ編集 - {name}")
    editor.geometry("1120x640")
    editor.minsize(960, 520)
    editor.configure(fg_color="#101114")
    editor.grid_columnconfigure(0, weight=1)
    editor.grid_rowconfigure(2, weight=1)

    row_widgets = []

    header = ctk.CTkFrame(editor, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
    header.grid_columnconfigure(0, weight=1)

    title = ctk.CTkLabel(
        header,
        text=name,
        font=ctk.CTkFont(size=20, weight="bold"),
        text_color="#F5F7FA",
        anchor="w",
    )
    title.grid(row=0, column=0, sticky="ew")

    summary_label = ctk.CTkLabel(
        header,
        text="",
        text_color="#B8C0CC",
        anchor="e",
    )
    summary_label.grid(row=0, column=1, sticky="e")

    column_header = ctk.CTkFrame(editor, corner_radius=8, fg_color="#20232B")
    column_header.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))
    column_header.grid_columnconfigure(1, weight=1)
    headers = [("#", 0, 42), ("待ち時間", 1, 110), ("ボタン", 2, 84),
               ("X", 3, 82), ("Y", 4, 82), ("クリック後の入力", 5, 180), ("操作", 6, 360)]
    for text, col, width in headers:
        ctk.CTkLabel(
            column_header,
            text=text,
            width=width,
            text_color="#C8D0DC",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=col, padx=6, pady=8, sticky="ew")

    rows_frame = ctk.CTkScrollableFrame(editor, corner_radius=10, fg_color="#17191F")
    rows_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 10))
    rows_frame.grid_columnconfigure(1, weight=1)

    footer = ctk.CTkFrame(editor, corner_radius=10, fg_color="#20232B")
    footer.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 16))
    footer.grid_columnconfigure((0, 1, 2, 3), weight=1)

    def collect_rows(show_error: bool = True):
        rows = []
        try:
            for widgets in row_widgets:
                elapsed = max(0.0, float(widgets["elapsed"].get()))
                x = int(float(widgets["x"].get()))
                y = int(float(widgets["y"].get()))
                button_name = button_label_to_name(widgets["button"].get())
                input_text = widgets["text"].get()
                rows.append((elapsed, x, y, button_name, input_text))
        except Exception:
            if show_error:
                messagebox.showwarning("入力エラー", "待ち時間/X/Y の数値を確認してください。", parent=editor)
            return None
        return rows

    def sync_from_entries() -> bool:
        rows = collect_rows(show_error=False)
        if rows is None:
            return False
        clicks[:] = [list(row) for row in rows]
        return True

    def update_summary():
        summary_label.configure(
            text=f"{len(clicks)}クリック / {format_duration(macro_duration_seconds(clicks))}"
        )

    def test_click(row_data):
        elapsed, x, y, button_name, input_text = normalize_click(row_data)

        def _worker():
            try:
                time.sleep(0.2)
                pyautogui.moveTo(x, y)
                pyautogui.click(button=button_name)
                paste_text_after_click(input_text)
                append_log(f"テスト: ({x}, {y}) {mouse_button_label(button_name)}")
            except Exception as e:
                append_log(f"テスト失敗: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def render_rows():
        for child in rows_frame.winfo_children():
            child.destroy()
        row_widgets.clear()
        update_summary()

        if not clicks:
            ctk.CTkLabel(
                rows_frame,
                text="クリックがありません。下の「クリック追加」で追加できます。",
                text_color="#8A93A5",
            ).grid(row=0, column=0, padx=12, pady=18, sticky="w")
            return

        for idx, click in enumerate(clicks):
            elapsed, x, y, button_name, input_text = normalize_click(click)
            row = ctk.CTkFrame(rows_frame, corner_radius=8, fg_color="#20232B")
            row.grid(row=idx, column=0, sticky="ew", padx=6, pady=(0, 6))
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row, text=str(idx + 1), width=42, text_color="#B8C0CC").grid(
                row=0, column=0, padx=(8, 4), pady=8
            )

            elapsed_entry = ctk.CTkEntry(row, width=110, justify="center", fg_color="#101114",
                                         border_color="#3A4250")
            elapsed_entry.insert(0, f"{float(elapsed):.2f}")
            elapsed_entry.grid(row=0, column=1, padx=4, pady=8, sticky="ew")

            button_var = tk.StringVar(master=editor, value=mouse_button_label(button_name))
            button_menu = ctk.CTkOptionMenu(row, width=84, values=["左", "右", "中"], variable=button_var)
            button_menu.grid(row=0, column=2, padx=4, pady=8)

            x_entry = ctk.CTkEntry(row, width=82, justify="center", fg_color="#101114",
                                   border_color="#3A4250")
            x_entry.insert(0, str(int(x)))
            x_entry.grid(row=0, column=3, padx=4, pady=8)

            y_entry = ctk.CTkEntry(row, width=82, justify="center", fg_color="#101114",
                                   border_color="#3A4250")
            y_entry.insert(0, str(int(y)))
            y_entry.grid(row=0, column=4, padx=4, pady=8)

            text_entry = ctk.CTkEntry(row, width=180, fg_color="#101114", border_color="#3A4250")
            text_entry.insert(0, input_text)
            text_entry.grid(row=0, column=5, padx=4, pady=8, sticky="ew")

            widgets = {
                "elapsed": elapsed_entry,
                "button": button_var,
                "x": x_entry,
                "y": y_entry,
                "text": text_entry,
            }
            row_widgets.append(widgets)

            def _click_pick(i=idx):
                if not sync_from_entries():
                    return

                def _capture(px, py, picked_button):
                    if i >= len(clicks):
                        return
                    clicks[i][1] = int(px)
                    clicks[i][2] = int(py)
                    clicks[i][3] = picked_button
                    render_rows()
                    append_log(
                        f"クリック指定: {i + 1}クリック目 → "
                        f"({int(px)}, {int(py)}) {mouse_button_label(picked_button)}"
                    )

                set_click_capture(_capture)
                append_log(f"{i + 1}クリック目: 直したい場所をクリックしてください")

            def _duplicate(i=idx):
                if not sync_from_entries():
                    return
                clicks.insert(i + 1, list(clicks[i]))
                render_rows()

            def _move(i=idx, delta=0):
                if not sync_from_entries():
                    return
                new_i = i + delta
                if new_i < 0 or new_i >= len(clicks):
                    return
                clicks[i], clicks[new_i] = clicks[new_i], clicks[i]
                render_rows()

            def _delete(i=idx):
                if not sync_from_entries():
                    return
                clicks.pop(i)
                render_rows()

            def _test(i=idx):
                rows = collect_rows()
                if rows is None:
                    return
                test_click(rows[i])

            def _test_from(i=idx):
                rows = collect_rows()
                if rows is None:
                    return
                start_click_test_replay(rows[i:], f"{name} {i + 1}クリック目から")

            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.grid(row=0, column=6, padx=(4, 8), pady=8, sticky="e")
            ctk.CTkButton(actions, text="クリック指定", width=86, height=28, command=_click_pick).grid(
                row=0, column=0, padx=2
            )
            ctk.CTkButton(actions, text="↑", width=32, height=28, command=lambda i=idx: _move(i, -1)).grid(
                row=0, column=1, padx=2
            )
            ctk.CTkButton(actions, text="↓", width=32, height=28, command=lambda i=idx: _move(i, 1)).grid(
                row=0, column=2, padx=2
            )
            ctk.CTkButton(actions, text="複製", width=52, height=28, command=_duplicate).grid(
                row=0, column=3, padx=2
            )
            ctk.CTkButton(actions, text="単体", width=52, height=28, command=_test).grid(
                row=0, column=4, padx=2
            )
            ctk.CTkButton(actions, text="以降", width=52, height=28, command=_test_from).grid(
                row=0, column=5, padx=2
            )
            ctk.CTkButton(actions, text="削除", width=52, height=28,
                          fg_color="#C0392B", hover_color="#E74C3C", command=_delete).grid(
                row=0, column=6, padx=2
            )

    def add_click():
        if not sync_from_entries():
            return
        px, py = pyautogui.position()
        clicks.append([0.0, int(px), int(py), "left", ""])
        render_rows()

    def save_editor():
        global recorded_clicks
        clear_click_capture()
        rows = collect_rows()
        if rows is None:
            return
        try:
            write_macro_clicks(name, rows)
            if current_macro_name == name:
                with lock:
                    recorded_clicks = list(rows)
            update_macro_label()
            refresh_macro_list(select_name=name)
            refresh_combo_list()
            append_log(f"編集保存: {name} ({len(rows)}クリック / {format_duration(macro_duration_seconds(rows))})")
            editor.destroy()
        except Exception as e:
            messagebox.showerror("保存失敗", str(e), parent=editor)

    ctk.CTkButton(footer, text="クリック追加", height=34, command=add_click).grid(
        row=0, column=0, padx=8, pady=10, sticky="ew"
    )
    ctk.CTkButton(footer, text="保存", height=34, command=save_editor).grid(
        row=0, column=1, padx=8, pady=10, sticky="ew"
    )
    ctk.CTkButton(footer, text="キャンセル", height=34, fg_color="#3F4654", hover_color="#535D70",
                  command=lambda: (clear_click_capture(), editor.destroy())).grid(
        row=0, column=2, padx=8, pady=10, sticky="ew"
    )

    render_rows()
    editor.protocol("WM_DELETE_WINDOW", lambda: (clear_click_capture(), editor.destroy()))
    editor.after(100, editor.focus_force)


# =========================================================
#  複数リスト
# =========================================================
def refresh_combo_list():
    global selected_combo_index
    if selected_combo_index is not None and selected_combo_index >= len(combo_plan):
        selected_combo_index = len(combo_plan) - 1 if combo_plan else None

    if combo_steps_frame is None:
        update_combo_summary()
        return

    for child in combo_steps_frame.winfo_children():
        child.destroy()

    for idx, item in enumerate(combo_plan, start=1):
        render_combo_step_row(idx - 1, item)

    update_combo_summary()
    update_play_mode_status()


def render_combo_step_row(index: int, item: dict):
    selected = selected_combo_index == index
    loops = normalize_loop_count(item.get("loops", 1))
    seconds = get_macro_duration_seconds(item["name"]) * loops
    bg = theme_pair("combo_selected") if selected else theme_pair("panel")
    border = theme_pair("focus") if selected else theme_pair("line")

    row = ctk.CTkFrame(
        combo_steps_frame,
        corner_radius=8,
        fg_color=bg,
        border_width=1,
        border_color=border,
    )
    row.grid(row=index, column=0, sticky="ew", padx=6, pady=(0, 6))
    row.grid_columnconfigure(1, weight=1)

    index_label = ctk.CTkLabel(
        row,
        text=str(index + 1),
        width=24,
        text_color=theme_pair("muted"),
        font=ctk.CTkFont(size=12, weight="bold"),
    )
    index_label.grid(row=0, column=0, rowspan=2, padx=(8, 6), pady=8, sticky="ns")

    name_label = ctk.CTkLabel(
        row,
        text=item["name"],
        text_color=theme_pair("text"),
        font=ctk.CTkFont(size=13, weight="bold"),
        anchor="w",
    )
    name_label.grid(row=0, column=1, padx=(0, 8), pady=(8, 0), sticky="ew")

    time_label = ctk.CTkLabel(
        row,
        text=f"{format_duration(seconds)}",
        text_color=theme_pair("muted"),
        font=ctk.CTkFont(size=11),
        anchor="w",
    )
    time_label.grid(row=1, column=1, padx=(0, 8), pady=(0, 8), sticky="ew")

    ctk.CTkLabel(row, text="x", text_color=theme_pair("muted"), width=12).grid(
        row=0, column=2, rowspan=2, padx=(0, 4), pady=8
    )
    loop_entry = ctk.CTkEntry(
        row,
        width=58,
        height=30,
        justify="center",
        fg_color=theme_pair("panel"),
        border_color=theme_pair("line_strong"),
        text_color=theme_pair("text"),
    )
    loop_entry.insert(0, str(loops))
    loop_entry.grid(row=0, column=3, rowspan=2, padx=(0, 8), pady=8)

    def _select(_event=None, i=index):
        select_combo_step(i)

    def _focus_entry(_event=None, i=index):
        select_combo_step(i, refresh=False)

    def _drag_start(event=None, i=index):
        start_combo_drag(i)

    def _drag_release(event, i=index):
        finish_combo_drag(event.y_root)

    def _update(_event=None, i=index, entry=loop_entry):
        update_combo_step_loops(i, entry.get())

    def _commit(_event=None, i=index, entry=loop_entry):
        update_combo_step_loops(i, entry.get())
        refresh_combo_list()

    for widget in (row, index_label, name_label, time_label):
        widget.bind("<ButtonPress-1>", _drag_start)
        widget.bind("<ButtonRelease-1>", _drag_release)
    loop_entry.bind("<FocusIn>", _focus_entry)
    loop_entry.bind("<KeyRelease>", _update)
    loop_entry.bind("<Return>", _commit)
    loop_entry.bind("<FocusOut>", _commit)


def select_combo_step(index: int, refresh: bool = True):
    global selected_combo_index
    if index < 0 or index >= len(combo_plan):
        return
    selected_combo_index = index
    if refresh:
        refresh_combo_list()


def start_combo_drag(index: int):
    global combo_drag_index, selected_combo_index
    if index < 0 or index >= len(combo_plan):
        return
    combo_drag_index = index
    selected_combo_index = index


def finish_combo_drag(y_root: int):
    global combo_drag_index, selected_combo_index
    if combo_drag_index is None:
        return
    from_idx = combo_drag_index
    combo_drag_index = None

    if from_idx < 0 or from_idx >= len(combo_plan):
        return

    to_idx = get_combo_drop_index(y_root)
    if to_idx is None or to_idx == from_idx:
        selected_combo_index = from_idx
        refresh_combo_list()
        return

    item = combo_plan.pop(from_idx)
    if to_idx > from_idx:
        to_idx -= 1
    to_idx = max(0, min(to_idx, len(combo_plan)))
    combo_plan.insert(to_idx, item)
    selected_combo_index = to_idx
    refresh_combo_list()
    save_config(silent=True)


def get_combo_drop_index(y_root: int) -> int | None:
    if combo_steps_frame is None or not combo_plan:
        return None
    rows = sorted(combo_steps_frame.winfo_children(), key=lambda child: child.grid_info().get("row", 0))
    if not rows:
        return None

    for idx, row in enumerate(rows):
        try:
            midpoint = row.winfo_rooty() + (row.winfo_height() / 2)
        except Exception:
            continue
        if y_root < midpoint:
            return idx
    return len(rows)


def update_combo_step_loops(index: int, value):
    if index < 0 or index >= len(combo_plan):
        return
    combo_plan[index]["loops"] = normalize_loop_count(value)
    update_combo_summary()
    save_config(silent=True)


def update_combo_summary():
    if combo_summary_label is None:
        return
    one_round = 0.0
    for item in combo_plan:
        one_round += get_macro_duration_seconds(item["name"]) * normalize_loop_count(item.get("loops", 1))
    outer = normalize_loop_count(combo_outer_loop_var.get() if combo_outer_loop_var else 1)
    combo_summary_label.configure(
        text=f"リスト1周: {format_duration(one_round)} / 全体{outer}回: {format_duration(one_round * outer)}"
    )
    update_dashboard()


def add_selected_macro_to_combo():
    name = get_selected_macro_name()
    if not name:
        append_log("追加するマクロを選択してください")
        return
    loops = 1
    combo_plan.append({"name": name, "loops": loops})
    select_combo_step(len(combo_plan) - 1)
    set_play_mode("playlist")
    refresh_combo_list()
    save_config(silent=True)
    append_log(f"追加: {name} x{loops}")


def get_selected_combo_index() -> int | None:
    if selected_combo_index is None:
        return None
    if selected_combo_index < 0 or selected_combo_index >= len(combo_plan):
        return None
    return selected_combo_index


def remove_selected_combo_step():
    idx = get_selected_combo_index()
    if idx is None:
        append_log("複数リストを選択してください")
        return
    removed = combo_plan.pop(idx)
    select_combo_step(min(idx, len(combo_plan) - 1)) if combo_plan else clear_combo_selection()
    refresh_combo_list()
    save_config(silent=True)
    append_log(f"複数リストから削除: {removed['name']}")


def clear_combo_plan():
    combo_plan.clear()
    clear_combo_selection()
    refresh_combo_list()
    save_config(silent=True)
    append_log("複数リストをクリア")


def clear_combo_selection():
    global selected_combo_index
    selected_combo_index = None


def move_combo_step(delta: int, warn_missing: bool = True) -> bool:
    global selected_combo_index
    idx = get_selected_combo_index()
    if idx is None:
        if warn_missing:
            append_log("複数リストを選択してください")
        return False
    new_idx = idx + delta
    if new_idx < 0 or new_idx >= len(combo_plan):
        return False
    combo_plan[idx], combo_plan[new_idx] = combo_plan[new_idx], combo_plan[idx]
    selected_combo_index = new_idx
    refresh_combo_list()
    save_config(silent=True)
    return True


def start_combo_move_repeat(delta: int):
    global combo_move_job
    stop_combo_move_repeat()
    move_combo_step(delta)

    def _repeat():
        global combo_move_job
        move_combo_step(delta, warn_missing=False)
        combo_move_job = app.after(160, _repeat)

    if app is not None:
        combo_move_job = app.after(360, _repeat)


def stop_combo_move_repeat():
    global combo_move_job
    if combo_move_job is None or app is None:
        combo_move_job = None
        return
    try:
        app.after_cancel(combo_move_job)
    except Exception:
        pass
    combo_move_job = None


def bind_hold_move(button, delta: int):
    button.bind("<ButtonPress-1>", lambda _e: start_combo_move_repeat(delta))
    button.bind("<ButtonRelease-1>", lambda _e: stop_combo_move_repeat())
    button.bind("<Leave>", lambda _e: stop_combo_move_repeat())


def build_combo_replay_plan() -> list:
    if not combo_plan:
        raise ValueError("複数リストが空です")

    plan = []
    for item in combo_plan:
        name = item.get("name", "")
        loops = normalize_loop_count(item.get("loops", 1))
        clicks = read_macro_clicks(name)
        if not clicks:
            raise ValueError(f"マクロ '{name}' に記録がありません")
        plan.append({
            "name": name,
            "loops": loops,
            "clicks": clicks,
            "duration": macro_duration_seconds(clicks),
        })
    return plan


# =========================================================
#  UI
# =========================================================
ACTION_LABELS = {
    "record_start": "録画開始",
    "record_stop":  "録画停止",
    "replay_start": "再生開始",
    "force_stop":   "全停止",
    "quit":         "終了",
}


def build_ui():
    global app, log_box, loop_var, play_mode_var, play_mode_status_label, badge_record, badge_replay
    global playlist_state_label, playlist_toggle_button
    global macro_listbox, current_macro_label
    global combo_listbox, combo_steps_frame, combo_outer_loop_var, combo_summary_label
    global log_panel, log_body_frame, log_toggle_button, log_status_label, log_clear_button
    global dashboard_macro_label, dashboard_mode_label, dashboard_plan_label, dashboard_status_label, dashboard_status_strip

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    app = ctk.CTk()
    app.title("Mouse Macro NEW")
    app.geometry("1360x840")
    app.minsize(1120, 700)
    app.configure(fg_color="#101114")

    app.grid_columnconfigure(0, weight=0, minsize=360)
    app.grid_columnconfigure(1, weight=1, minsize=440)
    app.grid_columnconfigure(2, weight=0, minsize=360)
    app.grid_rowconfigure(0, weight=1)
    app.grid_rowconfigure(1, weight=0)

    # 左
    left = ctk.CTkFrame(app, corner_radius=12, width=360, fg_color="#17191F")
    left.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
    left.grid_propagate(False)
    left.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(
        left,
        text=f"Mouse Macro NEW  v{APP_VERSION}",
        font=ctk.CTkFont(size=24, weight="bold"),
        text_color="#F5F7FA"
    ).grid(
        row=0, column=0, sticky="w", padx=18, pady=(18, 4)
    )

    current_macro_label = ctk.CTkLabel(left, text=f"選択中: {current_macro_name}",
                                       font=ctk.CTkFont(size=12), text_color="#B8C0CC")
    current_macro_label.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 10))

    badge_row = ctk.CTkFrame(left, corner_radius=10, fg_color="#20232B")
    badge_row.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))
    badge_row.grid_columnconfigure((0, 1), weight=1)

    badge_record = ctk.CTkLabel(badge_row, text="REC", corner_radius=8, fg_color="#30333C",
                                font=ctk.CTkFont(size=13, weight="bold"))
    badge_record.grid(row=0, column=0, sticky="ew", padx=(10, 5), pady=10)

    badge_replay = ctk.CTkLabel(badge_row, text="PLAY", corner_radius=8, fg_color="#30333C",
                                font=ctk.CTkFont(size=13, weight="bold"))
    badge_replay.grid(row=0, column=1, sticky="ew", padx=(5, 10), pady=10)

    loop_box = ctk.CTkFrame(left, corner_radius=10, fg_color="#20232B")
    loop_box.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 10))
    loop_box.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(loop_box, text="単体ループ", font=ctk.CTkFont(size=14, weight="bold")).grid(
        row=0, column=0, padx=12, pady=12, sticky="w"
    )
    loop_var = tk.IntVar(master=app, value=1)
    loop_entry = ctk.CTkEntry(loop_box, textvariable=loop_var, justify="center", width=96,
                              fg_color="#101114", border_color="#3A4250")
    loop_entry.grid(
        row=0, column=1, padx=12, pady=12, sticky="e"
    )
    loop_entry.bind("<KeyRelease>", lambda _e: update_dashboard())

    mode_box = ctk.CTkFrame(left, corner_radius=10, fg_color="#20232B")
    mode_box.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 10))
    mode_box.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(mode_box, text="再生対象", font=ctk.CTkFont(size=14, weight="bold")).grid(
        row=0, column=0, sticky="w", padx=12, pady=(12, 6)
    )
    play_mode_var = tk.StringVar(master=app, value=play_mode_to_label(DEFAULTS["play_mode"]))
    ctk.CTkSegmentedButton(
        mode_box,
        values=["単体", "複数"],
        variable=play_mode_var,
        command=lambda value: (update_play_mode_status(), update_combo_summary(), save_config(silent=True)),
    ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
    play_mode_status_label = ctk.CTkLabel(
        mode_box,
        text="F3: 単体",
        text_color="#B8C0CC",
        anchor="w",
        font=ctk.CTkFont(size=12),
    )
    play_mode_status_label.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

    ctk.CTkButton(left, text="録画開始  F1", height=42, command=start_recording).grid(
        row=5, column=0, padx=18, pady=(0, 8), sticky="ew"
    )
    ctk.CTkButton(left, text="録画停止  F2", height=42, command=stop_recording).grid(
        row=6, column=0, padx=18, pady=(0, 8), sticky="ew"
    )
    ctk.CTkButton(left, text="再生開始  F3", height=46,
                  font=ctk.CTkFont(size=14, weight="bold"), command=start_replay).grid(
        row=7, column=0, padx=18, pady=(0, 8), sticky="ew"
    )
    ctk.CTkButton(left, text="強制停止  F4", height=42,
                  fg_color="#C0392B", hover_color="#E74C3C",
                  command=force_stop).grid(
        row=8, column=0, padx=18, pady=(0, 8), sticky="ew"
    )

    bottom_btns = ctk.CTkFrame(left, corner_radius=10, fg_color="#20232B")
    bottom_btns.grid(row=9, column=0, sticky="ew", padx=18, pady=(8, 10))
    bottom_btns.grid_columnconfigure((0, 1), weight=1)

    ctk.CTkButton(bottom_btns, text="設定保存", height=34, fg_color="#3F4654", hover_color="#535D70",
                  command=save_config).grid(row=0, column=0, padx=6, pady=8, sticky="ew")
    ctk.CTkButton(bottom_btns, text="終了  Esc", height=34, fg_color="#3F4654", hover_color="#535D70",
                  command=safe_quit).grid(row=0, column=1, padx=6, pady=8, sticky="ew")

    hk_container = ctk.CTkFrame(left, corner_radius=10, fg_color="#20232B")
    hk_container.grid(row=10, column=0, sticky="nsew", padx=18, pady=(0, 18))
    hk_container.grid_rowconfigure(1, weight=1)
    hk_container.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(hk_container, text="ショートカット",
                 font=ctk.CTkFont(size=15, weight="bold"), text_color="#F5F7FA").grid(
        row=0, column=0, sticky="w", padx=12, pady=(12, 6)
    )

    hk_scroll = ctk.CTkScrollableFrame(hk_container, corner_radius=8, fg_color="#181B22")
    hk_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
    hk_scroll.grid_columnconfigure(0, weight=0)
    hk_scroll.grid_columnconfigure(1, weight=1)
    hk_scroll.grid_columnconfigure(2, weight=0)

    entries.clear()
    row = 0
    for action in ["record_start", "record_stop", "replay_start", "force_stop", "quit"]:
        ctk.CTkLabel(hk_scroll, text=ACTION_LABELS[action], text_color="#C8D0DC").grid(
            row=row, column=0, padx=8, pady=6, sticky="w"
        )

        ent = ctk.CTkEntry(hk_scroll, height=30, fg_color="#101114", border_color="#3A4250")
        ent.grid(row=row, column=1, padx=8, pady=6, sticky="ew")
        entries[action] = ent

        ent.bind("<Return>", lambda e, a=action, w=ent: apply_hotkey_from_entry(a, w))

        ctk.CTkButton(
            hk_scroll, text="適用", width=54, height=28,
            fg_color="#3F4654", hover_color="#535D70",
            command=lambda a=action, e=ent: apply_hotkey_from_entry(a, e)
        ).grid(row=row, column=2, padx=(0, 8), pady=6, sticky="e")

        row += 1

    left.grid_rowconfigure(10, weight=1)

    # 中央ステータス
    center = ctk.CTkFrame(app, corner_radius=12, fg_color="#17191F")
    center.grid(row=0, column=1, sticky="nsew", padx=(0, 8), pady=16)
    center.grid_rowconfigure(3, weight=1)
    center.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(center, text="実行状況", font=ctk.CTkFont(size=20, weight="bold"),
                 text_color="#F5F7FA").grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10))

    dashboard_grid = ctk.CTkFrame(center, fg_color="transparent")
    dashboard_grid.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
    dashboard_grid.grid_columnconfigure((0, 1), weight=1)
    dashboard_grid.grid_rowconfigure((0, 1), weight=0)

    def make_dashboard_card(row_idx, col_idx, title, accent="#3D8BFF"):
        card = ctk.CTkFrame(dashboard_grid, corner_radius=10, fg_color="#20232B",
                            border_width=1, border_color="#2B303B")
        card.grid(row=row_idx, column=col_idx, sticky="nsew", padx=5, pady=5)
        card.grid_columnconfigure(1, weight=1)
        strip = ctk.CTkFrame(card, width=4, corner_radius=3, fg_color=accent)
        strip.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(10, 8), pady=10)
        ctk.CTkLabel(card, text=title, text_color="#8A93A5",
                     font=ctk.CTkFont(size=12, weight="bold"), anchor="w").grid(
            row=0, column=1, sticky="ew", padx=(0, 12), pady=(10, 2)
        )
        value = ctk.CTkLabel(card, text="-", text_color="#F5F7FA",
                             font=ctk.CTkFont(size=14, weight="bold"),
                             anchor="w", justify="left")
        value.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 10))
        card.bind(
            "<Configure>",
            lambda event, label=value: label.configure(wraplength=max(160, event.width - 48)),
        )
        return value, strip

    dashboard_macro_label, _ = make_dashboard_card(0, 0, "選択中のマクロ", "#3D8BFF")
    dashboard_mode_label, _ = make_dashboard_card(0, 1, "再生対象", "#57C785")
    dashboard_plan_label, _ = make_dashboard_card(1, 0, "複数リスト時間", "#F0B35A")
    dashboard_status_label, dashboard_status_strip = make_dashboard_card(1, 1, "最後の状態", "#B8C0CC")

    quick_actions = ctk.CTkFrame(center, corner_radius=10, fg_color="#20232B")
    quick_actions.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
    quick_actions.grid_columnconfigure((0, 1, 2), weight=1)
    ctk.CTkButton(quick_actions, text="選択マクロを編集", height=34,
                  command=open_macro_editor).grid(row=0, column=0, padx=8, pady=10, sticky="ew")
    ctk.CTkButton(quick_actions, text="リストに追加", height=34,
                  command=add_selected_macro_to_combo).grid(row=0, column=1, padx=8, pady=10, sticky="ew")
    ctk.CTkButton(quick_actions, text="再生開始", height=34,
                  fg_color="#3F4654", hover_color="#535D70",
                  command=start_replay).grid(row=0, column=2, padx=8, pady=10, sticky="ew")

    # 右マクロ管理
    right = ctk.CTkFrame(app, corner_radius=12, width=360, fg_color="#17191F")
    right.grid(row=0, column=2, sticky="nsew", padx=(0, 16), pady=16)
    right.grid_propagate(False)
    right.grid_rowconfigure(2, weight=1)
    right.grid_rowconfigure(3, weight=1)
    right.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(right, text="マクロ管理", font=ctk.CTkFont(size=20, weight="bold"),
                 text_color="#F5F7FA").grid(
        row=0, column=0, sticky="w", padx=18, pady=(18, 10)
    )

    btn_frame = ctk.CTkFrame(right, corner_radius=10, fg_color="#20232B")
    btn_frame.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))
    btn_frame.grid_columnconfigure((0, 1, 2), weight=1)

    ctk.CTkButton(btn_frame, text="新規", height=30, command=new_macro).grid(
        row=0, column=0, padx=4, pady=8, sticky="ew"
    )
    ctk.CTkButton(btn_frame, text="編集", height=30, command=open_macro_editor).grid(
        row=0, column=1, padx=4, pady=8, sticky="ew"
    )
    ctk.CTkButton(btn_frame, text="複製", height=30,
                  fg_color="#3F4654", hover_color="#535D70",
                  command=duplicate_selected_macro).grid(
        row=0, column=2, padx=4, pady=8, sticky="ew"
    )
    ctk.CTkButton(btn_frame, text="名前変更", height=30,
                  fg_color="#3F4654", hover_color="#535D70",
                  command=rename_selected_macro).grid(
        row=1, column=0, columnspan=2, padx=4, pady=(0, 8), sticky="ew"
    )
    ctk.CTkButton(btn_frame, text="削除", height=30,
                  fg_color="#C0392B", hover_color="#E74C3C",
                  command=delete_selected_macro).grid(
        row=1, column=2, padx=4, pady=(0, 8), sticky="ew"
    )

    list_frame = ctk.CTkFrame(right, corner_radius=10, fg_color="#20232B")
    list_frame.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 12))
    list_frame.grid_rowconfigure(0, weight=1)
    list_frame.grid_columnconfigure(0, weight=1)

    macro_listbox = tk.Listbox(
        list_frame,
        bg="#111318", fg="#F5F7FA",
        selectbackground="#2C6FB7", selectforeground="#FFFFFF",
        font=(UI_FONT_FAMILY, 11),
        relief="flat", borderwidth=0, highlightthickness=0,
        activestyle="none",
        exportselection=False
    )
    macro_listbox.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
    macro_listbox.bind("<<ListboxSelect>>", on_macro_select)

    scrollbar = ctk.CTkScrollbar(list_frame, command=macro_listbox.yview)
    scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
    macro_listbox.configure(yscrollcommand=scrollbar.set)

    combo_frame = ctk.CTkFrame(right, corner_radius=10, fg_color="#20232B")
    combo_frame.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 18))
    combo_frame.grid_columnconfigure(0, weight=1)
    combo_frame.grid_rowconfigure(4, weight=1)

    ctk.CTkLabel(combo_frame, text="複数リスト", font=ctk.CTkFont(size=15, weight="bold"),
                 text_color="#F5F7FA").grid(
        row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 6)
    )

    combo_controls = ctk.CTkFrame(combo_frame, corner_radius=8, fg_color="#181B22")
    combo_controls.grid(row=1, column=0, columnspan=4, sticky="ew", padx=8, pady=(0, 6))
    combo_controls.grid_columnconfigure(0, weight=1)

    ctk.CTkButton(combo_controls, text="選択マクロを追加", height=32, command=add_selected_macro_to_combo).grid(
        row=0, column=0, padx=8, pady=8, sticky="ew"
    )

    outer_controls = ctk.CTkFrame(combo_frame, corner_radius=8, fg_color="#181B22")
    outer_controls.grid(row=2, column=0, columnspan=4, sticky="ew", padx=8, pady=(0, 6))
    outer_controls.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(outer_controls, text="全体ループ", text_color="#C8D0DC").grid(
        row=0, column=0, padx=(8, 4), pady=8, sticky="w"
    )
    combo_outer_loop_var = tk.IntVar(master=app, value=1)
    outer_loop_entry = ctk.CTkEntry(outer_controls, textvariable=combo_outer_loop_var, justify="center",
                                    width=64, height=30, fg_color="#101114", border_color="#3A4250")
    outer_loop_entry.grid(
        row=0, column=1, padx=4, pady=8, sticky="w"
    )
    outer_loop_entry.bind("<KeyRelease>", lambda _e: update_combo_summary())
    ctk.CTkButton(outer_controls, text="保存", width=58, height=30,
                  fg_color="#3F4654", hover_color="#535D70", command=save_config).grid(
        row=0, column=2, padx=(4, 8), pady=8, sticky="e"
    )

    combo_summary_label = ctk.CTkLabel(
        combo_frame,
        text="リスト1周: 0.0秒 / 全体1回: 0.0秒",
        font=ctk.CTkFont(size=12),
        text_color="#B8C0CC",
        anchor="w",
    )
    combo_summary_label.grid(row=3, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 6))

    combo_steps_frame = ctk.CTkScrollableFrame(
        combo_frame,
        corner_radius=8,
        fg_color="#111318",
    )
    combo_steps_frame.grid(row=4, column=0, columnspan=4, sticky="nsew", padx=8, pady=(0, 6))
    combo_steps_frame.grid_columnconfigure(0, weight=1)

    combo_buttons = ctk.CTkFrame(combo_frame, corner_radius=8, fg_color="#181B22")
    combo_buttons.grid(row=5, column=0, columnspan=4, sticky="ew", padx=8, pady=(0, 8))
    combo_buttons.grid_columnconfigure((0, 1, 2, 3), weight=1)

    up_button = ctk.CTkButton(combo_buttons, text="↑", width=36, height=30,
                              fg_color="#3F4654", hover_color="#535D70")
    up_button.grid(
        row=0, column=0, padx=3, pady=6, sticky="ew"
    )
    bind_hold_move(up_button, -1)

    down_button = ctk.CTkButton(combo_buttons, text="↓", width=36, height=30,
                                fg_color="#3F4654", hover_color="#535D70")
    down_button.grid(
        row=0, column=1, padx=3, pady=6, sticky="ew"
    )
    bind_hold_move(down_button, 1)
    ctk.CTkButton(combo_buttons, text="削除", height=30,
                  fg_color="#3F4654", hover_color="#535D70",
                  command=remove_selected_combo_step).grid(
        row=0, column=2, padx=3, pady=6, sticky="ew"
    )
    ctk.CTkButton(combo_buttons, text="クリア", height=30,
                  fg_color="#3F4654", hover_color="#535D70",
                  command=clear_combo_plan).grid(
        row=0, column=3, padx=3, pady=6, sticky="ew"
    )

    # 下部ログドロワー
    log_panel = ctk.CTkFrame(app, corner_radius=12, fg_color="#17191F")
    log_panel.grid(row=1, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 16))
    log_panel.grid_columnconfigure(0, weight=1)

    log_header = ctk.CTkFrame(log_panel, fg_color="transparent")
    log_header.grid(row=0, column=0, sticky="ew", padx=12, pady=8)
    log_header.grid_columnconfigure(1, weight=1)

    log_toggle_button = ctk.CTkButton(
        log_header,
        text="⌃",
        width=34,
        height=30,
        fg_color="#3F4654",
        hover_color="#535D70",
        command=toggle_log_panel,
    )
    log_toggle_button.grid(row=0, column=0, padx=(0, 8), sticky="w")

    log_status_label = ctk.CTkLabel(
        log_header,
        text="ログは空です",
        text_color="#B8C0CC",
        anchor="w",
        font=ctk.CTkFont(size=13, weight="bold"),
    )
    log_status_label.grid(row=0, column=1, sticky="ew", padx=(0, 8))

    ctk.CTkLabel(log_header, text="ログ", text_color="#8A93A5",
                 font=ctk.CTkFont(size=12, weight="bold")).grid(
        row=0, column=2, padx=(0, 8), sticky="e"
    )
    log_clear_button = ctk.CTkButton(
        log_header,
        text="クリア",
        width=72,
        height=30,
        fg_color="#3F4654",
        hover_color="#535D70",
        command=clear_log,
    )
    log_clear_button.grid(row=0, column=3, sticky="e")

    log_body_frame = ctk.CTkFrame(log_panel, fg_color="transparent")
    log_body_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
    log_body_frame.grid_columnconfigure(0, weight=1)

    log_box = ctk.CTkTextbox(
        log_body_frame,
        height=104,
        corner_radius=10,
        wrap="word",
        fg_color="#101114",
        border_width=1,
        border_color="#2B303B",
        text_color="#D8DEE9",
    )
    log_box.grid(row=0, column=0, sticky="ew")
    log_box.configure(state="disabled")
    set_log_expanded(False)

    refresh_hotkey_entries()
    refresh_macro_list(select_name=current_macro_name)
    refresh_combo_list()

    append_log("起動しました")

    update_badges()


def build_ui_reset():
    global app, log_box, loop_var, play_mode_var, appearance_mode_var, play_mode_status_label, badge_record, badge_replay
    global playlist_state_label, playlist_toggle_button
    global main_workspace, playlist_panel
    global macro_listbox, current_macro_label
    global combo_steps_frame, combo_outer_loop_var, combo_summary_label
    global log_panel, log_body_frame, log_toggle_button, log_status_label, log_clear_button
    global dashboard_macro_label, dashboard_mode_label, dashboard_plan_label, dashboard_status_label, dashboard_status_strip

    bg = theme_pair("bg")
    panel = theme_pair("panel")
    panel_2 = theme_pair("panel_2")
    surface = theme_pair("surface")
    line = theme_pair("line")
    line_strong = theme_pair("line_strong")
    text = theme_pair("text")
    muted = theme_pair("muted")
    blue = theme_pair("blue")
    blue_hover = theme_pair("blue_hover")
    red = theme_pair("red")
    red_hover = theme_pair("red_hover")
    subtle = theme_pair("subtle")
    subtle_hover = theme_pair("subtle_hover")

    dashboard_macro_label = None
    dashboard_mode_label = None
    dashboard_plan_label = None
    dashboard_status_strip = None

    ctk.set_appearance_mode(ctk_appearance_name(appearance_mode))
    ctk.set_default_color_theme("blue")
    configure_default_fonts()

    app = ctk.CTk()
    configure_default_fonts(app)
    app.title("Mouse Macro NEW")
    app.geometry("1360x840")
    app.minsize(1120, 700)
    app.configure(fg_color=bg)
    app.grid_columnconfigure(0, weight=1)
    app.grid_rowconfigure(1, weight=1)

    def panel_frame(parent, **kwargs):
        return ctk.CTkFrame(
            parent,
            corner_radius=8,
            fg_color=panel,
            border_width=1,
            border_color=line,
            **kwargs,
        )

    def header(parent, title, right_text=None):
        frame = ctk.CTkFrame(parent, corner_radius=0, fg_color=panel_2)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame,
            text=title,
            text_color=text,
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=12)
        if right_text:
            ctk.CTkLabel(
                frame,
                text=right_text,
                text_color=muted,
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=1, padx=14, pady=12, sticky="e")
        return frame

    def button(parent, label, command, kind="primary", **grid):
        if kind == "danger":
            fg, hover, fg_text = red, red_hover, "#FFFFFF"
        elif kind == "subtle":
            fg, hover, fg_text = subtle, subtle_hover, text
        else:
            fg, hover, fg_text = blue, blue_hover, "#FFFFFF"
        btn = ctk.CTkButton(
            parent,
            text=label,
            height=42,
            corner_radius=7,
            fg_color=fg,
            hover_color=hover,
            text_color=fg_text,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=command,
        )
        btn.grid(**grid)
        return btn

    # Top status bar
    topbar = panel_frame(app)
    topbar.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))
    topbar.grid_columnconfigure(1, weight=1)

    brand = ctk.CTkFrame(topbar, fg_color="transparent")
    brand.grid(row=0, column=0, padx=14, pady=10, sticky="w")
    ctk.CTkLabel(
        brand,
        text="Mouse Macro NEW",
        text_color=text,
        font=ctk.CTkFont(size=20, weight="bold"),
        anchor="w",
    ).grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(
        brand,
        text=f"v{APP_VERSION}",
        text_color=muted,
        font=ctk.CTkFont(size=12),
        anchor="w",
    ).grid(row=1, column=0, sticky="w")

    context = ctk.CTkFrame(topbar, fg_color="transparent")
    context.grid(row=0, column=1, sticky="ew", padx=10, pady=10)
    context.grid_columnconfigure((0, 1, 2), weight=0)

    dashboard_status_label = ctk.CTkLabel(
        context,
        text="待機中",
        text_color=theme_pair("success_text"),
        fg_color=panel_2,
        corner_radius=999,
        height=30,
        padx=12,
        font=ctk.CTkFont(size=13, weight="bold"),
    )
    dashboard_status_label.grid(row=0, column=0, padx=(0, 8), sticky="w")

    current_macro_label = ctk.CTkLabel(
        context,
        text=f"選択中: {current_macro_name}",
        text_color=text,
        fg_color=panel_2,
        corner_radius=999,
        height=30,
        padx=12,
        font=ctk.CTkFont(size=13, weight="bold"),
    )
    current_macro_label.grid(row=0, column=1, padx=(0, 8), sticky="w")

    play_mode_status_label = ctk.CTkLabel(
        context,
        text="F3: 単体",
        text_color=text,
        fg_color=panel_2,
        corner_radius=999,
        height=30,
        padx=12,
        font=ctk.CTkFont(size=13, weight="bold"),
    )
    play_mode_status_label.grid(row=0, column=2, sticky="w")

    play_mode_var = tk.StringVar(master=app, value=play_mode_to_label(DEFAULTS["play_mode"]))
    mode_switch = ctk.CTkSegmentedButton(
        topbar,
        values=["単体", "複数"],
        variable=play_mode_var,
        width=180,
        height=34,
        selected_color=blue,
        selected_hover_color=blue_hover,
        unselected_color=panel,
        unselected_hover_color=panel_2,
        text_color=text,
        command=lambda _value: (update_play_mode_status(), update_combo_summary(), save_config(silent=True)),
    )
    mode_switch.grid(row=0, column=2, padx=14, pady=10, sticky="e")

    appearance_mode_var = tk.StringVar(master=app, value=appearance_mode_to_label(appearance_mode))
    appearance_switch = ctk.CTkSegmentedButton(
        topbar,
        values=["ライト", "ダーク"],
        variable=appearance_mode_var,
        width=132,
        height=34,
        selected_color=subtle,
        selected_hover_color=subtle_hover,
        unselected_color=panel,
        unselected_hover_color=panel_2,
        text_color=text,
        command=set_appearance_mode_from_label,
    )
    appearance_switch.grid(row=0, column=3, padx=(0, 14), pady=10, sticky="e")

    # Main workspace
    main = ctk.CTkFrame(app, fg_color="transparent")
    main_workspace = main
    main.grid(row=1, column=0, sticky="nsew", padx=14, pady=6)
    main.grid_columnconfigure(0, weight=0, minsize=300)
    main.grid_columnconfigure(1, weight=1, minsize=420)
    main.grid_columnconfigure(2, weight=0, minsize=370)
    main.grid_rowconfigure(0, weight=1)

    # Left: execution controls
    left = panel_frame(main)
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
    left.grid_columnconfigure(0, weight=1)
    left.grid_rowconfigure(3, weight=1)
    header(left, "実行", "最優先操作").grid(row=0, column=0, sticky="ew")

    left_body = ctk.CTkFrame(left, fg_color="transparent")
    left_body.grid(row=1, column=0, sticky="ew", padx=12, pady=12)
    left_body.grid_columnconfigure((0, 1), weight=1)

    button(left_body, "録画開始  F1", start_recording, row=0, column=0, padx=(0, 4), pady=(0, 8), sticky="ew")
    button(left_body, "録画停止  F2", stop_recording, row=0, column=1, padx=(4, 0), pady=(0, 8), sticky="ew")
    button(left_body, "再生開始  F3", start_replay, row=1, column=0, padx=(0, 4), pady=(0, 8), sticky="ew")
    button(left_body, "全停止  F4", force_stop, "danger", row=1, column=1, padx=(4, 0), pady=(0, 8), sticky="ew")

    badge_row = ctk.CTkFrame(left_body, fg_color="transparent")
    badge_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 8))
    badge_row.grid_columnconfigure((0, 1), weight=1)
    badge_record = ctk.CTkLabel(
        badge_row,
        text="REC",
        corner_radius=7,
        fg_color=subtle,
        text_color=text,
        height=30,
        font=ctk.CTkFont(size=12, weight="bold"),
    )
    badge_record.grid(row=0, column=0, sticky="ew", padx=(0, 4))
    badge_replay = ctk.CTkLabel(
        badge_row,
        text="PLAY",
        corner_radius=7,
        fg_color=subtle,
        text_color=text,
        height=30,
        font=ctk.CTkFont(size=12, weight="bold"),
    )
    badge_replay.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    loop_box = ctk.CTkFrame(left_body, fg_color=panel, corner_radius=7, border_width=1, border_color=line)
    loop_box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
    loop_box.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(loop_box, text="単体ループ", text_color=muted, font=ctk.CTkFont(weight="bold")).grid(
        row=0, column=0, padx=10, pady=8, sticky="w"
    )
    loop_var = tk.IntVar(master=app, value=1)
    loop_entry = ctk.CTkEntry(
        loop_box,
        textvariable=loop_var,
        width=82,
        height=30,
        justify="right",
        fg_color=panel,
        border_color=line_strong,
        text_color=text,
    )
    loop_entry.grid(row=0, column=1, padx=10, pady=8, sticky="e")

    outer_box = ctk.CTkFrame(left_body, fg_color=panel, corner_radius=7, border_width=1, border_color=line)
    outer_box.grid(row=4, column=0, columnspan=2, sticky="ew")
    outer_box.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(outer_box, text="リスト全体", text_color=muted, font=ctk.CTkFont(weight="bold")).grid(
        row=0, column=0, padx=10, pady=8, sticky="w"
    )
    combo_outer_loop_var = tk.IntVar(master=app, value=1)
    outer_loop_entry = ctk.CTkEntry(
        outer_box,
        textvariable=combo_outer_loop_var,
        width=82,
        height=30,
        justify="right",
        fg_color=panel,
        border_color=line_strong,
        text_color=text,
    )
    outer_loop_entry.grid(row=0, column=1, padx=10, pady=8, sticky="e")
    outer_loop_entry.bind("<KeyRelease>", lambda _e: update_combo_summary())

    shortcut_frame = ctk.CTkFrame(left, fg_color="transparent")
    shortcut_frame.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 12))
    shortcut_frame.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(
        shortcut_frame,
        text="ショートカット",
        text_color=text,
        font=ctk.CTkFont(size=14, weight="bold"),
        anchor="w",
    ).grid(row=0, column=0, columnspan=3, sticky="ew", pady=(2, 8))

    entries.clear()
    row = 1
    for action in ["record_start", "record_stop", "replay_start", "force_stop", "quit"]:
        ctk.CTkLabel(shortcut_frame, text=ACTION_LABELS[action], text_color=muted).grid(
            row=row, column=0, padx=(0, 8), pady=4, sticky="w"
        )
        ent = ctk.CTkEntry(
            shortcut_frame,
            height=30,
            fg_color=panel,
            border_color=line_strong,
            text_color=text,
            width=70,
            justify="center",
        )
        ent.grid(row=row, column=1, padx=4, pady=4, sticky="ew")
        entries[action] = ent
        ent.bind("<Return>", lambda _e, a=action, w=ent: apply_hotkey_from_entry(a, w))
        ctk.CTkButton(
            shortcut_frame,
            text="適用",
            width=52,
            height=30,
            corner_radius=6,
            fg_color=subtle,
            hover_color=subtle_hover,
            text_color=text,
            command=lambda a=action, e=ent: apply_hotkey_from_entry(a, e),
        ).grid(row=row, column=2, padx=(4, 0), pady=4)
        row += 1

    bottom_buttons = ctk.CTkFrame(left, fg_color="transparent")
    bottom_buttons.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))
    bottom_buttons.grid_columnconfigure((0, 1), weight=1)
    button(bottom_buttons, "設定保存", save_config, "subtle", row=0, column=0, padx=(0, 4), sticky="ew")
    button(bottom_buttons, "終了  Esc", safe_quit, "subtle", row=0, column=1, padx=(4, 0), sticky="ew")

    # Center: macro library
    center = panel_frame(main)
    center.grid(row=0, column=1, sticky="nsew", padx=(0, 12))
    center.grid_columnconfigure(0, weight=1)
    center.grid_rowconfigure(2, weight=1)
    header(center, "マクロ", "一覧").grid(row=0, column=0, sticky="ew")

    macro_toolbar = ctk.CTkFrame(center, fg_color=panel)
    macro_toolbar.grid(row=1, column=0, sticky="ew", padx=12, pady=12)
    macro_toolbar.grid_columnconfigure(0, weight=1)
    search_entry = ctk.CTkEntry(
        macro_toolbar,
        height=34,
        placeholder_text="マクロを検索",
        fg_color=panel,
        border_color=line_strong,
        text_color=text,
    )
    search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    button(macro_toolbar, "新規", new_macro, row=0, column=1, padx=4, sticky="ew")
    button(macro_toolbar, "編集", open_macro_editor, "subtle", row=0, column=2, padx=4, sticky="ew")
    button(macro_toolbar, "複製", duplicate_selected_macro, "subtle", row=0, column=3, padx=(4, 0), sticky="ew")

    list_frame = ctk.CTkFrame(center, corner_radius=0, fg_color=panel)
    list_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 0))
    list_frame.grid_rowconfigure(0, weight=1)
    list_frame.grid_columnconfigure(0, weight=1)

    macro_listbox = tk.Listbox(
        list_frame,
        bg=theme_color("list_bg"),
        fg=theme_color("text"),
        selectbackground=theme_color("list_selected"),
        selectforeground=theme_color("text"),
        font=(UI_FONT_FAMILY, 11),
        relief="flat",
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=theme_color("line"),
        highlightcolor=theme_color("focus"),
        activestyle="none",
        exportselection=False,
    )
    macro_listbox.grid(row=0, column=0, sticky="nsew")
    macro_listbox.bind("<<ListboxSelect>>", on_macro_select)

    scrollbar = ctk.CTkScrollbar(list_frame, command=macro_listbox.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    macro_listbox.configure(yscrollcommand=scrollbar.set)

    macro_actions = ctk.CTkFrame(center, fg_color=panel_2, corner_radius=0)
    macro_actions.grid(row=3, column=0, sticky="ew")
    macro_actions.grid_columnconfigure(0, weight=1)
    ctk.CTkLabel(
        macro_actions,
        text="選択したマクロの編集、複製、削除ができます",
        text_color=muted,
        anchor="w",
        font=ctk.CTkFont(size=12),
    ).grid(row=0, column=0, sticky="ew", padx=12, pady=10)
    button(macro_actions, "名前変更", rename_selected_macro, "subtle", row=0, column=1, padx=4, pady=8, sticky="e")
    button(macro_actions, "削除", delete_selected_macro, "subtle", row=0, column=2, padx=(4, 12), pady=8, sticky="e")

    # Right: playlist
    right = panel_frame(main)
    playlist_panel = right
    right.grid(row=0, column=2, sticky="nsew")
    right.grid_columnconfigure(0, weight=1)
    right.grid_rowconfigure(3, weight=1)
    header(right, "複数リスト", "ドラッグで並べ替え").grid(row=0, column=0, sticky="ew")

    playlist_top = ctk.CTkFrame(right, fg_color=panel)
    playlist_top.grid(row=1, column=0, sticky="ew", padx=12, pady=12)
    playlist_top.grid_columnconfigure(0, weight=1)
    button(playlist_top, "選択マクロを追加", add_selected_macro_to_combo, row=0, column=0, sticky="ew")

    playlist_mode_row = ctk.CTkFrame(playlist_top, fg_color=panel_2, corner_radius=7)
    playlist_mode_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
    playlist_mode_row.grid_columnconfigure(0, weight=1)
    playlist_state_label = ctk.CTkLabel(
        playlist_mode_row,
        text="OFF: F3は単体",
        text_color=muted,
        anchor="w",
        font=ctk.CTkFont(size=12, weight="bold"),
    )
    playlist_state_label.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
    playlist_toggle_button = ctk.CTkButton(
        playlist_mode_row,
        text="複数をON",
        width=120,
        height=28,
        corner_radius=6,
        fg_color=subtle,
        hover_color=subtle_hover,
        text_color=text,
        command=toggle_playlist_mode,
    )
    playlist_toggle_button.grid(row=0, column=1, padx=(4, 8), pady=7, sticky="e")

    combo_summary_label = ctk.CTkLabel(
        playlist_top,
        text="リスト1周: 0.0秒 / 全体1回: 0.0秒",
        text_color=text,
        fg_color=panel_2,
        corner_radius=7,
        height=34,
        font=ctk.CTkFont(size=12, weight="bold"),
        anchor="center",
    )
    combo_summary_label.grid(row=2, column=0, sticky="ew", pady=(10, 0))

    combo_steps_frame = ctk.CTkScrollableFrame(
        right,
        corner_radius=8,
        fg_color=surface,
        border_width=1,
        border_color=line,
    )
    combo_steps_frame.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 10))
    combo_steps_frame.grid_columnconfigure(0, weight=1)

    combo_buttons = ctk.CTkFrame(right, fg_color=panel_2, corner_radius=0)
    combo_buttons.grid(row=4, column=0, sticky="ew")
    combo_buttons.grid_columnconfigure((2, 3), weight=1)
    up_button = ctk.CTkButton(
        combo_buttons,
        text="↑",
        width=34,
        height=34,
        fg_color=panel,
        hover_color=panel_2,
        text_color=text,
        border_width=1,
        border_color=line,
    )
    up_button.grid(row=0, column=0, padx=(12, 4), pady=10)
    bind_hold_move(up_button, -1)
    down_button = ctk.CTkButton(
        combo_buttons,
        text="↓",
        width=34,
        height=34,
        fg_color=panel,
        hover_color=panel_2,
        text_color=text,
        border_width=1,
        border_color=line,
    )
    down_button.grid(row=0, column=1, padx=4, pady=10)
    bind_hold_move(down_button, 1)
    button(combo_buttons, "削除", remove_selected_combo_step, "subtle", row=0, column=2, padx=4, pady=10, sticky="ew")
    button(combo_buttons, "クリア", clear_combo_plan, "subtle", row=0, column=3, padx=(4, 12), pady=10, sticky="ew")

    # Bottom status/log drawer
    log_panel = panel_frame(app)
    log_panel.grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 14))
    log_panel.grid_columnconfigure(0, weight=1)

    log_header = ctk.CTkFrame(log_panel, fg_color="transparent")
    log_header.grid(row=0, column=0, sticky="ew", padx=10, pady=6)
    log_header.grid_columnconfigure(1, weight=1)

    log_toggle_button = ctk.CTkButton(
        log_header,
        text="⌃",
        width=34,
        height=32,
        corner_radius=6,
        fg_color=panel,
        hover_color=panel_2,
        text_color=text,
        border_width=1,
        border_color=line,
        command=toggle_log_panel,
    )
    log_toggle_button.grid(row=0, column=0, padx=(0, 8), sticky="w")

    log_status_label = ctk.CTkLabel(
        log_header,
        text="ログは空です",
        text_color=theme_pair("success_text"),
        anchor="w",
        font=ctk.CTkFont(size=13, weight="bold"),
    )
    log_status_label.grid(row=0, column=1, sticky="ew", padx=(0, 8))
    ctk.CTkLabel(log_header, text="ログ", text_color=muted, font=ctk.CTkFont(size=12)).grid(
        row=0, column=2, padx=(0, 8), sticky="e"
    )
    log_clear_button = ctk.CTkButton(
        log_header,
        text="クリア",
        width=72,
        height=32,
        corner_radius=6,
        fg_color=subtle,
        hover_color=subtle_hover,
        text_color=text,
        command=clear_log,
    )
    log_clear_button.grid(row=0, column=3, sticky="e")

    log_body_frame = ctk.CTkFrame(log_panel, fg_color="transparent")
    log_body_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
    log_body_frame.grid_columnconfigure(0, weight=1)

    log_box = ctk.CTkTextbox(
        log_body_frame,
        height=96,
        corner_radius=8,
        wrap="word",
        fg_color=theme_pair("log_bg"),
        border_width=1,
        border_color=line,
        text_color=theme_pair("log_text"),
        font=ctk.CTkFont(size=12),
    )
    log_box.grid(row=0, column=0, sticky="ew")
    log_box.configure(state="disabled")
    set_log_expanded(False)

    refresh_hotkey_entries()
    refresh_macro_list(select_name=current_macro_name)
    refresh_combo_list()
    append_log("起動しました")
    update_badges()


# =========================================================
#  メイン
# =========================================================
def main():
    global mouse_listener, keyboard_listener, appearance_mode

    appearance_mode = read_saved_appearance_mode()
    rebuild_hotkey_sets()
    build_ui_reset()

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
