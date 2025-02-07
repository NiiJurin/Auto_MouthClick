import time
import threading
from pynput import mouse, keyboard
import pyautogui

# -----------------------------
# グローバル変数
# -----------------------------
recorded_clicks = []  # [(elapsed, x, y), ...]
recording = False
replaying = False
force_stop = False
last_click_time = None

mouse_listener = None
keyboard_listener = None

# -----------------------------
# マウスイベント (クリック)
# -----------------------------
def on_click(x, y, button, pressed):
    global recording, last_click_time
    # デバッグ: 毎回押下を表示
    print(f"[DEBUG on_click] pressed={pressed}, button={button}, x={x}, y={y}, recording={recording}")

    if recording and pressed:  # 録画中 & ボタン押下時
        now = time.time()
        if last_click_time is None:
            elapsed = 0
        else:
            elapsed = now - last_click_time
        last_click_time = now
        recorded_clicks.append((elapsed, x, y))
        print(f"[RECORD] click at ({x}, {y}), interval={elapsed:.2f}s")

# -----------------------------
# キーボードイベント (押下)
# -----------------------------
def on_press(key):
    print(f"[DEBUG on_press] key={key}")

    if key == keyboard.Key.f1:
        start_recording()
    elif key == keyboard.Key.f2:
        stop_recording()
    elif key == keyboard.Key.f3:
        start_replay()
    elif key == keyboard.Key.f4:
        force_stop_replay()
    elif key == keyboard.Key.esc:
        # ESC でプログラム終了
        raise KeyboardInterrupt

# -----------------------------
# キーボードイベント (離し)
# -----------------------------
def on_release(key):
    pass

# -----------------------------
# 録画開始 (F1)
# -----------------------------
def start_recording():
    global recording, last_click_time, recorded_clicks
    if recording:
        print("[INFO] すでに録画中です。")
        return

    print("[INFO] 録画開始(即時)")
    recorded_clicks.clear()
    last_click_time = None
    recording = True

# -----------------------------
# 録画停止 (F2)
# -----------------------------
def stop_recording():
    global recording
    if recording:
        recording = False
        print("[INFO] 録画を停止しました。記録件数:", len(recorded_clicks))
    else:
        print("[INFO] 録画は開始されていません。")

# -----------------------------
# 再生開始 (F3)
# -----------------------------
def start_replay():
    global recording, replaying
    if recording:
        print("[INFO] 録画中は再生できません。")
        return
    if replaying:
        print("[INFO] すでに再生中です。")
        return
    if not recorded_clicks:
        print("[INFO] 記録がありません。先に録画してください。")
        return

    # 別スレッドで再生
    replay_thread = threading.Thread(target=replay_clicks, daemon=True)
    replay_thread.start()

# -----------------------------
# 再生強制停止 (F4)
# -----------------------------
def force_stop_replay():
    global force_stop
    force_stop = True
    print("[INFO] 再生を強制停止リクエスト")

# -----------------------------
# 再生処理
# -----------------------------
def replay_clicks():
    global replaying, force_stop
    replaying = True
    print("[INFO] Start replaying...")

    for i, (elapsed, x, y) in enumerate(recorded_clicks):
        if force_stop:
            print("[INFO] 再生が強制停止されました。")
            force_stop = False
            break

        time.sleep(elapsed)

        if force_stop:
            print("[INFO] 再生が強制停止されました。")
            force_stop = False
            break

        pyautogui.moveTo(x, y)
        pyautogui.click()
        print(f"[REPLAY] ({i+1}/{len(recorded_clicks)}) click at ({x}, {y}) after {elapsed:.2f}s")

    if not force_stop:
        print("[INFO] Replay finished.")
    replaying = False

# -----------------------------
# メインループ
# -----------------------------
def main():
    print("=== F1-F4 制御サンプル ===")
    print(" F1 => 録画開始")
    print(" F2 => 録画停止")
    print(" F3 => 再生開始")
    print(" F4 => 再生強制停止")
    print(" ESC => プログラム終了 (Ctrl+CでもOK)\n")

    global mouse_listener, keyboard_listener

    mouse_listener = mouse.Listener(on_click=on_click)
    keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)

    mouse_listener.start()
    keyboard_listener.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] 強制終了します。")
    finally:
        mouse_listener.stop()
        keyboard_listener.stop()

if __name__ == "__main__":
    main()
