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
last_click_time = None

mouse_listener = None
keyboard_listener = None
root = None
log_area = None
loop_count_var = None

lock = threading.Lock()
stop_event = threading.Event()   # ★ force_stop の代わり（安全）


# -----------------------------
# GUIログ出力（スレッドセーフ版）
# -----------------------------
def append_log(message: str):
    print(message)

    if root is None or log_area is None:
        return

    def _write():
        log_area.insert(tk.END, message + "\n")
        log_area.see(tk.END)

    # ★Tkinterは他スレッドから触れない → afterでメインスレッド実行
    root.after(0, _write)


# -----------------------------
# マウスイベント (クリック)
# -----------------------------
def on_click(x, y, button, pressed):
    global recording, last_click_time
    if recording and pressed:
        now = time.time()
        with lock:
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
            root.quit()
    except Exception as e:
        append_log(f"[ERROR on_press] {e}")


# -----------------------------
# 録画開始
# -----------------------------
def start_recording():
    global recording, last_click_time
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

    append_log("[INFO] 録画開始(即時)")


# -----------------------------
# 録画停止
# -----------------------------
def stop_recording():
    global recording
    with lock:
        if recording:
            recording = False
            count = len(recorded_clicks)
        else:
            count = None

    if count is None:
        append_log("[INFO] 録画は開始されていません。")
    else:
        append_log("[INFO] 録画を停止しました。")
        append_log(f"[INFO] 記録件数: {count}")


# -----------------------------
# 再生開始
# -----------------------------
def start_replay():
    global recording, replaying

    with lock:
        if recording:
            append_log("[INFO] 録画中は再生できません。")
            return
        if replaying:
            append_log("[INFO] すでに再生中です。")
            return
        if not recorded_clicks:
            append_log("[INFO] 記録がありません。先に録画してください。")
            return

        # ★ここで先に True にして多重起動防止
        replaying = True

    stop_event.clear()
    threading.Thread(target=replay_clicks_with_loop, daemon=True).start()


# -----------------------------
# 再生強制停止
# -----------------------------
def force_stop_replay():
    stop_event.set()
    append_log("[INFO] 再生を強制停止リクエスト")


# -----------------------------
# ループ再生処理
# -----------------------------
def replay_clicks_with_loop():
    global replaying

    # Spinboxからループ回数を取得（GUIスレッドじゃなくてもIntVar.getは大抵OKだが、安全寄りに読む）
    try:
        count = int(loop_count_var.get())
    except Exception:
        count = 1

    # ★録画データのスナップショット（再生中に変更されても壊れない）
    with lock:
        seq = list(recorded_clicks)

    append_log(f"[INFO] {count}回ループ再生を開始します...")

    stopped = False

    for loop_i in range(1, count + 1):
        if stop_event.is_set():
            stopped = True
            append_log("[INFO] 再生が強制停止されました。")
            break

        append_log(f"== ループ {loop_i}/{count} 回目 ==")
        start_time = time.time()

        for i, (elapsed, x, y) in enumerate(seq):
            if stop_event.is_set():
                stopped = True
                append_log("[INFO] 再生が強制停止されました。")
                break

            time.sleep(elapsed)

            if stop_event.is_set():
                stopped = True
                append_log("[INFO] 再生が強制停止されました。")
                break

            pyautogui.moveTo(x, y)
            pyautogui.click()
            append_log(f"[REPLAY] loop={loop_i}, step=({i+1}/{len(seq)}) "
                       f"click at ({x}, {y}) after {elapsed:.2f}s")

        if stopped:
            break

        elapsed_total = time.time() - start_time
        append_log(f"== {loop_i}回目の再生完了 (合計{elapsed_total:.2f}s) ==")

    if not stopped:
        append_log("[INFO] ループ再生が完了しました。")

    with lock:
        replaying = False


# -----------------------------
# GUI作成
# -----------------------------
def create_gui():
    global root, log_area, loop_count_var

    root = tk.Tk()
    root.title("マウス録画・再生 (Tkinter + Fキー + ループ)")

    frame_buttons = tk.Frame(root)
    frame_buttons.pack(pady=5)

    tk.Button(frame_buttons, text="録画開始", command=start_recording, width=10).grid(row=0, column=0, padx=5)
    tk.Button(frame_buttons, text="録画停止", command=stop_recording, width=10).grid(row=0, column=1, padx=5)
    tk.Button(frame_buttons, text="再生開始", command=start_replay, width=10).grid(row=0, column=2, padx=5)
    tk.Button(frame_buttons, text="再生強制停止", command=force_stop_replay, width=12).grid(row=0, column=3, padx=5)
    tk.Button(frame_buttons, text="終了", command=root.quit, width=5).grid(row=0, column=4, padx=5)

    tk.Label(root, text="ループ回数:").pack()
    loop_count_var = tk.IntVar(value=1)
    tk.Spinbox(root, from_=1, to=999, textvariable=loop_count_var, width=5).pack()

    log_area = scrolledtext.ScrolledText(root, width=80, height=15)
    log_area.pack(padx=5, pady=5)


# -----------------------------
# メインループ
# -----------------------------
def main():
    global mouse_listener, keyboard_listener

    create_gui()
    append_log("[INFO] アプリ起動")

    mouse_listener = mouse.Listener(on_click=on_click)
    mouse_listener.start()

    keyboard_listener = keyboard.Listener(on_press=on_press)
    keyboard_listener.start()

    root.mainloop()

    if mouse_listener:
        mouse_listener.stop()
        mouse_listener.join()
    if keyboard_listener:
        keyboard_listener.stop()
        keyboard_listener.join()

    append_log("[INFO] アプリ終了")


if __name__ == "__main__":
    main()
