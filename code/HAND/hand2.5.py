import cv2
import mediapipe as mp
import numpy as np
import time

# MediaPipe Hands 초기화
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,  # 인식할 손의 개수를 2개로 변경
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5,
)
mp_drawing = mp.solutions.drawing_utils

# 웹캠 열기
cap = cv2.VideoCapture(0)

# 해상도 설정
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

# 자동 화이트 밸런스 설정 (선택 사항)
cap.set(cv2.CAP_PROP_AUTO_WB, 1)

# 손가락 잡기 감지 임계값 (엄지와 검지 끝 사이 거리)
CATCH_THRESHOLD = 0.05
# 이전 잡기 감지 상태 기록 변수 (터미널 출력용)
prev_catch_state = [False, False]  # 손이 두 개이므로 리스트로 변경
# 손 크기(손목-중지 길이) 제한 (정규화된 좌표 기준)
MIN_HAND_LENGTH = 0.3
# MAX_HAND_LENGTH  = 0.3 # 큰 손도 인식할 수 있도록 최댓값 해제

def detect_catch(hand_landmarks, image_shape):
    """
    엄지와 검지 끝 거리를 계산하여 잡기 동작을 감지합니다.

    Args:
        hand_landmarks: 손 랜드마크 객체
        image_shape: 이미지의 (높이, 너비) 튜플

    Returns:
        True if 잡기 동작 감지, False otherwise
    """
    if hand_landmarks is None:
        return False

    # 엄지 끝 & 검지 끝 좌표 가져오기
    try:
        thumb_tip = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
        index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]

        # 이미지 크기를 고려하여 거리 계산 (정규화된 좌표 사용)
        distance = np.sqrt(
            (thumb_tip.x - index_tip.x) ** 2 + (thumb_tip.y - index_tip.y) ** 2
        )

        return distance < CATCH_THRESHOLD
    except:
        return False

def calculate_distance(p1, p2):
    """두 랜드마크 사이의 거리를 계산합니다."""
    return np.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)

while cap.isOpened():
    success, image = cap.read()
    if not success:
        print("웹캠을 찾을 수 없습니다.")
        continue

    # 색상 보정 (YCrCb 공간에서 조정)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(image)
    cr = cv2.add(cr, 13)
    cb = cv2.subtract(cb, 20)
    image = cv2.merge([y, cr, cb])
    image = cv2.cvtColor(image, cv2.COLOR_YCrCb2BGR)

    # 이미지에서 손 감지 (RGB 변환 필요)
    image.flags.writeable = False
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = hands.process(image_rgb)
    image.flags.writeable = True

    image_height, image_width, _ = image.shape

    if results.multi_hand_landmarks:
        for hand_index, hand_landmarks in enumerate(results.multi_hand_landmarks):
            # 손 크기(손목-중지 길이) 계산
            wrist = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST]
            middle_finger_tip = hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_TIP]
            hand_length = calculate_distance(wrist, middle_finger_tip)

            # 손 크기 제한 필터링
            if hand_length < MIN_HAND_LENGTH:
                continue  # 손 크기가 작으면 무시

            # 1. 손 그리기
            mp_drawing.draw_landmarks(
                image,
                hand_landmarks,
                mp_hands.HAND_CONNECTIONS,
                mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=4),
                mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=2),
            )

            # 2. 각 랜드마크 좌표 및 거리 표시
            for i in range(len(mp_hands.HandLandmark) - 1):
                landmark_1 = hand_landmarks.landmark[i]

                # 검지와 엄지 사이 선은 그리지 않음
                if i != 3:
                    landmark_2 = hand_landmarks.landmark[i + 1]
                else:
                    continue

                # 랜드마크 좌표 (픽셀 좌표로 변환)
                cx1, cy1 = int(landmark_1.x * image_width), int(landmark_1.y * image_height)
                cx2, cy2 = int(landmark_2.x * image_width), int(landmark_2.y * image_height)

                # 거리를 이미지에 표시
                dist = calculate_distance(landmark_1, landmark_2)
                cv2.putText(
                    image,
                    f"{dist:.3f}",
                    ((cx1 + cx2) // 2, (cy1 + cy2) // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

                # 선 그리기
                cv2.line(image, (cx1, cy1), (cx2, cy2), (255, 0, 0), 2)

            # 3. 잡기 감지
            current_catch_state = detect_catch(hand_landmarks, image.shape)

            # 화면에 CATCH 표시 (잡고 있는 동안 계속 표시)
            if current_catch_state:
                cv2.putText(
                    image,
                    "CATCH",
                    (10 + hand_index * 200, 50),  # 두 번째 손은 옆에 텍스트 표시
                    cv2.FONT_HERSHEY_SIMPLEX,
                    2,
                    (0, 0, 255),
                    3,
                    cv2.LINE_AA,
                )

            # 터미널에 CATCH 출력 (한 번만, 각 손에 대해)
            if current_catch_state and not prev_catch_state[hand_index]:
                print(f"CATCH (Hand {hand_index + 1})")  # 손 번호(1 또는 2) 출력

            prev_catch_state[hand_index] = current_catch_state
        
        # prev_catch_state 초기화
        for hand_index in range(len(results.multi_hand_landmarks),2):
            prev_catch_state[hand_index] = False

    # 결과 이미지 보여주기
    cv2.imshow("MediaPipe Hands", image)

    if cv2.waitKey(5) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()