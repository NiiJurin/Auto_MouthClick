"""
GUI + Mouse Macro + Fキーホットキー Example with Loop Count
============================================================
- Tkinterを使った簡易GUI（録画開始 / 停止 / 再生 / 強制停止 / 終了）
- さらに F1～F4, Esc で各操作をホットキー呼び出し
- pynput でマウスクリックをフック (recording 中のみ記録)
- pyautogui で再生
- ★ ループ回数をSpinboxで入力し、その回数だけ再生を繰り返す

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

# ループ回数をGUIから取得するための変数 (IntVar)
loop_count_var = None

# -----------------------------
# マウスイベント (クリック)
# -----------------------------
def on_click(x, y, button, pressed):
    global recording, last_click_time
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
# キーボードイベント (F1～F4, Esc)
# -----------------------------
def on_press(key):
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
# 録画開始 (F1 or ボタン)
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
# 録画停止 (F2 or ボタン)
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
# 再生開始 (F3 or ボタン)
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

    replay_thread = threading.Thread(target=replay_clicks_with_loop, daemon=True)
    replay_thread.start()

# -----------------------------
# 再生強制停止 (F4 or ボタン)
# -----------------------------
def force_stop_replay():
    global force_stop
    force_stop = True
    append_log("[INFO] 再生を強制停止リクエスト")

# -----------------------------
# ループ再生処理
# -----------------------------
def replay_clicks_with_loop():
    """
    Spinboxに設定された回数だけ、recorded_clicksを繰り返し再生
    """
    global replaying, force_stop

    # Spinboxからループ回数を取得
    count = loop_count_var.get()
    append_log(f"[INFO] {count}回ループ再生を開始します...")

    replaying = True

    for loop_i in range(1, count + 1):
        # ループ開始チェック
        if force_stop:
            append_log("[INFO] 再生が強制停止されました。")
            force_stop = False
            break

        append_log(f"== ループ {loop_i}/{count} 回目 ==")
        start_time = time.time()

        # クリックシーケンス再生
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
            append_log(f"[REPLAY] loop={loop_i}, step=({i+1}/{len(recorded_clicks)}) "
                       f"click at ({x}, {y}) after {elapsed:.2f}s")

        if force_stop:
            break

        elapsed_total = time.time() - start_time
        append_log(f"== {loop_i}回目の再生完了 (合計{elapsed_total:.2f}s) ==")

    # ループを最後まで回った、または強制停止
    if not force_stop:
        append_log("[INFO] ループ再生が完了しました。")

    replaying = False
    force_stop = False

# -----------------------------
# GUI作成
# -----------------------------
def create_gui():
    global root, log_area, loop_count_var

    root = tk.Tk()
    root.title("マウス録画・再生 (Tkinter + Fキー + ループ)")

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

    # ループ回数を指定するSpinbox
    loop_label = tk.Label(root, text="ループ回数:")
    loop_label.pack()

    loop_count_var = tk.IntVar(value=1)
    loop_spin = tk.Spinbox(root, from_=1, to=999, textvariable=loop_count_var, width=5)
    loop_spin.pack()

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
