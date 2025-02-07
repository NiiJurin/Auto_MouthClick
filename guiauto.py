"""
GUI + Mouse Macro + Fキーホットキー Example
===========================================
- Tkinterを使った簡易GUI（録画開始 / 停止 / 再生 / 強制停止 / 終了）
- さらに F1～F4, Esc で各操作をホットキー呼び出し
- pynput でマウスクリックをフック (recording 中のみ記録)
- pyautogui で再生

PyInstaller でexe化:
  pip install pyinstaller
  pyinstaller --onefile gui_macro.py
"""

import time
import threading
import tkinter as tk
from tkinter import scrolledtext

import pyautogui
from pynput import mouse, keyboard

# -----------------------------
# グローバル変数
# -----------------------------
recorded_clicks = []   # [(elapsed, x, y), ...]
recording = False
replaying = False
force_stop = False
last_click_time = None

mouse_listener = None
keyboard_listener = None
root = None           # Tkinterメインウィンドウ
log_area = None       # ログ表示エリア (ScrolledText)

# -----------------------------
# マウスイベント (クリック)
# -----------------------------
def on_click(x, y, button, pressed):
    global recording, last_click_time
    # デバッグ表示してもよい
    #append_log(f"[DEBUG on_click] pressed={pressed}, x={x}, y={y}, button={button}, recording={recording}")

    if recording and pressed:
        now = time.time()
        if last_click_time is None:
            elapsed = 0
        else:
            elapsed = now - last_click_time
        last_click_time = now
        recorded_clicks.append((elapsed, x, y))
        append_log(f"[RECORD] click at ({x}, {y}), interval={elapsed:.2f}s")

# -----------------------------
# キーボードイベント (ホットキー)
# -----------------------------
def on_press(key):
    """Fキー or Esc で各機能を呼び出し"""
    #append_log(f"[DEBUG on_press] key={key}")
    try:
        if key == keyboard.Key.f1:
            start_recording()
        elif key == keyboard.Key.f2:
            stop_recording()
        elif key == keyboard.Key.f3:
            start_replay()
        elif key == keyboard.Key.f4:
            force_stop_replay()
        elif key == keyboard.Key.esc:
            append_log("[INFO] Esc pressed -> 終了します。")
            root.quit()  # Tkinterのメインループ終了
    except Exception as e:
        append_log(f"[ERROR on_press] {e}")

# -----------------------------
# GUIログ出力
# -----------------------------
def append_log(message):
    """コンソール + GUIテキストエリアに出力"""
    print(message)
    if log_area is not None:
        log_area.insert(tk.END, message + "\n")
        log_area.see(tk.END)

# -----------------------------
# ボタン操作: 録画開始
# -----------------------------
def start_recording():
    global recording, last_click_time, recorded_clicks
    if recording:
        append_log("[INFO] すでに録画中です。")
        return
    append_log("[INFO] 録画開始(即時)")

    recorded_clicks.clear()
    last_click_time = None
    recording = True

# -----------------------------
# ボタン操作: 録画停止
# -----------------------------
def stop_recording():
    global recording
    if recording:
        recording = False
        append_log("[INFO] 録画を停止しました。")
        append_log(f"[INFO] 記録件数: {len(recorded_clicks)}")
    else:
        append_log("[INFO] 録画は開始されていません。")

# -----------------------------
# ボタン操作: 再生開始
# -----------------------------
def start_replay():
    global recording, replaying
    if recording:
        append_log("[INFO] 録画中は再生できません。")
        return
    if replaying:
        append_log("[INFO] すでに再生中です。")
        return
    if not recorded_clicks:
        append_log("[INFO] 記録がありません。先に録画してください。")
        return

    replay_thread = threading.Thread(target=replay_clicks, daemon=True)
    replay_thread.start()

# -----------------------------
# ボタン操作: 再生強制停止
# -----------------------------
def force_stop_replay():
    global force_stop
    force_stop = True
    append_log("[INFO] 再生を強制停止リクエスト")

# -----------------------------
# 再生処理
# -----------------------------
def replay_clicks():
    global replaying, force_stop
    replaying = True
    append_log("[INFO] Start replaying...")

    for i, (elapsed, x, y) in enumerate(recorded_clicks):
        if force_stop:
            append_log("[INFO] 再生が強制停止されました。")
            force_stop = False
            break
        time.sleep(elapsed)
        if force_stop:
            append_log("[INFO] 再生が強制停止されました。")
            force_stop = False
            break
        pyautogui.moveTo(x, y)
        pyautogui.click()
        append_log(f"[REPLAY] ({i+1}/{len(recorded_clicks)}) click at ({x}, {y}) after {elapsed:.2f}s")

    if not force_stop:
        append_log("[INFO] Replay finished.")
    replaying = False

# -----------------------------
# GUI作成
# -----------------------------
def create_gui():
    global root, log_area

    root = tk.Tk()
    root.title("マウス録画・再生 (Tkinter + F1～F4)")

    frame_buttons = tk.Frame(root)
    frame_buttons.pack(pady=5)

    btn_record_start = tk.Button(frame_buttons, text="録画開始", command=start_recording, width=10)
    btn_record_start.grid(row=0, column=0, padx=5)

    btn_record_stop = tk.Button(frame_buttons, text="録画停止", command=stop_recording, width=10)
    btn_record_stop.grid(row=0, column=1, padx=5)

    btn_replay = tk.Button(frame_buttons, text="再生開始", command=start_replay, width=10)
    btn_replay.grid(row=0, column=2, padx=5)

    btn_force_stop = tk.Button(frame_buttons, text="再生強制停止", command=force_stop_replay, width=12)
    btn_force_stop.grid(row=0, column=3, padx=5)

    btn_quit = tk.Button(frame_buttons, text="終了", command=root.quit, width=5)
    btn_quit.grid(row=0, column=4, padx=5)

    # ログ表示エリア
    log_area = scrolledtext.ScrolledText(root, width=80, height=15)
    log_area.pack(padx=5, pady=5)

# -----------------------------
# メインループ
# -----------------------------
def main():
    global mouse_listener, keyboard_listener

    # 1) GUI作成
    create_gui()

    # 2) 初期ログ
    append_log("[INFO] アプリ起動")

    # 3) マウスリスナー開始
    mouse_listener = mouse.Listener(on_click=on_click)
    mouse_listener.start()

    # 4) キーボードリスナー開始 (F1,F2,F3,F4, Esc)
    keyboard_listener = keyboard.Listener(on_press=on_press)
    keyboard_listener.start()

    # 5) GUIのメインループ
    root.mainloop()

    # 6) GUI終了後、リスナーを停止
    if mouse_listener:
        mouse_listener.stop()
        mouse_listener.join()

    if keyboard_listener:
        keyboard_listener.stop()
        keyboard_listener.join()

    append_log("[INFO] アプリ終了")

if __name__ == "__main__":
    main()
