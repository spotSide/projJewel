import pyttsx3
import threading
import cv2
import asyncio
import time
from datetime import datetime  # 현재 시간 출력용
from test_depth import setup_depth_model, process_depth_sections, display_depth_sections
import sys
from io import StringIO

class TextToSpeech:
    def __init__(self, rate=150, volume=0.9, voice_index=0):
        """TTS 엔진 초기화 및 설정"""
        self.engine = pyttsx3.init()

        # 속도 및 볼륨 설정
        self.engine.setProperty('rate', rate)
        self.engine.setProperty('volume', volume)

        # 음성 설정
        voices = self.engine.getProperty('voices')
        if voice_index < len(voices):
            self.engine.setProperty('voice', voices[voice_index].id)
        else:
            print("Voice index out of range. Using default voice.")

        # 상태 변수
        self.last_tts_time = 0  # 마지막 TTS 실행 시간
        self.is_tts_busy = False  # 현재 TTS 실행 중인지 여부
        self.previous_decision = None  # 이전 출력된 상태 기록

    def speak(self, text):
        """주어진 텍스트를 비동기적으로 음성 출력"""
        if text is None:  # None 상태는 출력하지 않음
            return

        current_time = time.time()

        # TTS 실행 (7초 딜레이 확인)
        if current_time - self.last_tts_time >= 7:
            self.is_tts_busy = True
            self.last_tts_time = current_time
            self.previous_decision = text

            thread = threading.Thread(target=self._speak_thread, args=(text,))
            thread.start()

    def _speak_thread(self, text):
        """스레드에서 실제 TTS 음성 출력"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] TTS Output: {text}")  # 터미널 출력
        self.engine.say(text)
        self.engine.runAndWait()
        self.is_tts_busy = False  # 실행 완료 후 상태 해제

class FlagMonitor:
    def __init__(self):
        self.catch_flag = False  # Catch 플래그 상태
        self.detect_flag = False  # Detect 플래그 상태
        self.previous_combined_state = None  # 이전 결합 상태
        self.original_stdout = sys.stdout  # 원래 stdout 저장
        sys.stdout = self  # stdout 리다이렉트

    def write(self, text):
        """터미널 출력 감지 및 플래그 상태 업데이트"""
        # Catch 플래그 상태 업데이트
        if "catch flag - 5s" in text:
            self.catch_flag = True
        elif "catch end" in text:
            self.catch_flag = False

        # Detect 플래그 상태 업데이트
        if "class detect flag - 5s" in text:
            self.detect_flag = True
        elif "class flag end" in text:
            self.detect_flag = False

        # 원래 stdout에 출력
        self.original_stdout.write(text)

    def flush(self):
        """flush 호출을 위한 메서드 (stdout 요구사항)"""
        self.original_stdout.flush()

    async def monitor_flags(self):
        """플래그 상태를 지속적으로 모니터링 (둘 다 True일 때만 출력)"""
        while True:
            # 현재 상태 결합
            current_combined_state = (self.catch_flag and self.detect_flag)

            # 상태가 변경되었고, 둘 다 True인 경우에만 출력
            if current_combined_state and current_combined_state != self.previous_combined_state:
                print(f"[Monitor] Both Catch and Detect Flags are True!")
                self.previous_combined_state = current_combined_state

            # 상태가 False로 변경된 경우도 기록 (출력은 하지 않음)
            if not current_combined_state:
                self.previous_combined_state = current_combined_state

            # 프로그램 종료 조건 추가
            if not asyncio.get_event_loop().is_running():
                break

            await asyncio.sleep(0.1)  # 0.1초마다 상태 확인

class DepthWithTTS:
    def __init__(self, tts):
        """Depth 모델과 TTS를 결합한 클래스"""
        self.depth_processor = setup_depth_model()
        self.tts = tts
        self.last_tts_time = 0  # 마지막 TTS 출력 시간 초기화

    async def run(self, shared_data):
        """비동기적으로 뎁스 모델을 실행하고 결과를 TTS로 출력"""
        while shared_data['running']:
            frame = shared_data.get('frame')
            if frame is None:
                await asyncio.sleep(0)  # 이벤트 루프 양보
                continue

            try:
                # OpenVINO 뎁스 모델 처리
                depth_result = self.depth_processor.process_frame(frame)
                depth_map = (depth_result.squeeze(0) - depth_result.min()) / (depth_result.max() - depth_result.min())
                depth_frame = self.depth_processor.visualize_result(depth_result)

                # 깊이 섹션 분석
                decision = process_depth_sections(depth_map, num_rows=5, num_cols=5, threshold=0.8)

                # TTS로 결과 출력 (3초 딜레이 적용)
                current_time = asyncio.get_event_loop().time()
                if decision and current_time - self.last_tts_time >= 3:  # 3초 경과 확인
                    self.tts.speak(decision)
                    self.last_tts_time = current_time

                    # 현재 시간과 TTS 출력 로그
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{now}] TTS Output: {decision}")

                # 섹션이 표시된 뎁스 이미지
                depth_frame_with_sections = display_depth_sections(
                    depth_frame.copy(), depth_map, num_rows=5, num_cols=5, output_width=1280, output_height=720
                )

                # 텍스트 출력
                if decision:
                    cv2.putText(
                        depth_frame_with_sections,
                        decision,
                        (50, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.0, (0, 0, 255), 2, cv2.LINE_AA
                    )

                # 화면 출력
                cv2.imshow("Depth Estimation", depth_frame_with_sections)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    shared_data['running'] = False
                    break

            except Exception as e:
                print(f"Error in unified_depth_with_tts: {e}")
                shared_data['running'] = False
                break

            await asyncio.sleep(0)  # 이벤트 루프 양보

        cv2.destroyAllWindows()