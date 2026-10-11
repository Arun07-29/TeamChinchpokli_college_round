"""Handsfree Stage 2: hand cursor + optional pinch click + optional gesture scrolling.
Free local prototype. Press C to toggle click, S to toggle scrolling, Q/Esc to quit.
Clicking and scrolling start disabled for safety.
"""
import time
import cv2
import mediapipe as mp
import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01
screen_w, screen_h = pyautogui.size()
camera = cv2.VideoCapture(0)
if not camera.isOpened():
    raise RuntimeError("Could not open webcam. Close other apps using it and check Windows camera permissions.")

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
click_enabled = False
scroll_enabled = False
pinch_was_closed = False
last_click_time = 0.0
smooth_x, smooth_y = screen_w / 2, screen_h / 2
smoothing = 0.30
scroll_anchor_y = None

def finger_up(hand, tip_id, pip_id):
    return hand.landmark[tip_id].y < hand.landmark[pip_id].y

with mp_hands.Hands(static_image_mode=False, max_num_hands=1, model_complexity=0,
                    min_detection_confidence=0.6, min_tracking_confidence=0.6) as hands:
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("Could not read webcam frame.")
                break
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            cv2.putText(frame, f"CLICK: {'ON' if click_enabled else 'OFF'}  (C)",
                        (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                        (0, 200, 0) if click_enabled else (0, 170, 255), 2)
            cv2.putText(frame, f"SCROLL: {'ON' if scroll_enabled else 'OFF'}  (S)",
                        (12, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                        (0, 200, 0) if scroll_enabled else (0, 170, 255), 2)
            cv2.putText(frame, "Q/ESC: quit", (12, 84),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

            if result.multi_hand_landmarks:
                hand = result.multi_hand_landmarks[0]
                mp_draw.draw_landmarks(frame, hand, mp_hands.HAND_CONNECTIONS)
                thumb, index, middle = hand.landmark[4], hand.landmark[8], hand.landmark[12]
                index_up = finger_up(hand, 8, 6)
                middle_up = finger_up(hand, 12, 10)
                ring_up = finger_up(hand, 16, 14)
                pinky_up = finger_up(hand, 20, 18)
                scroll_pose = index_up and middle_up and not ring_up and not pinky_up
                pinch_dist = ((index.x-thumb.x)**2 + (index.y-thumb.y)**2)**0.5
                pinch_closed = pinch_dist < 0.045

                if scroll_enabled and scroll_pose:
                    pinch_was_closed = False
                    current_y = (index.y + middle.y) / 2
                    if scroll_anchor_y is not None:
                        delta = current_y - scroll_anchor_y
                        if abs(delta) > 0.025:
                            pyautogui.scroll(-int(delta * 850))
                            scroll_anchor_y = current_y
                    else:
                        scroll_anchor_y = current_y
                    cv2.putText(frame, "SCROLL GESTURE ACTIVE", (12, h-18),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
                else:
                    scroll_anchor_y = None
                    target_x = max(0, min(screen_w-1, (index.x-0.08)/0.84*screen_w))
                    target_y = max(0, min(screen_h-1, (index.y-0.08)/0.84*screen_h))
                    smooth_x += smoothing * (target_x-smooth_x)
                    smooth_y += smoothing * (target_y-smooth_y)
                    pyautogui.moveTo(int(smooth_x), int(smooth_y), _pause=False)
                    now = time.time()
                    if click_enabled and pinch_closed and not pinch_was_closed and now-last_click_time > 0.75:
                        pyautogui.click()
                        last_click_time = now
                    pinch_was_closed = pinch_closed
                    cv2.putText(frame, f"Pinch distance: {pinch_dist:.3f}", (12,h-18),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 2)
            else:
                pinch_was_closed = False
                scroll_anchor_y = None
                cv2.putText(frame, "Show one hand to the webcam", (12,h-18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)

            cv2.imshow("Handsfree Stage 2 - Click and Scroll", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("c"):
                click_enabled = not click_enabled
                pinch_was_closed = False
            elif key == ord("s"):
                scroll_enabled = not scroll_enabled
                scroll_anchor_y = None
    except pyautogui.FailSafeException:
        print("PyAutoGUI failsafe triggered; stopping safely.")
    finally:
        camera.release()
        cv2.destroyAllWindows()
