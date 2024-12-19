from test_depth import *
from test_hand import *
from test_webcam import *
from test_detect import *
from tts import *
import asyncio
import cv2

def initialize_components():
    """필요한 모든 구성 요소 초기화"""
    webcam_processor = WebcamProcessor(camera_id=0)  # 0: 일반 웹캠, 4: 리얼센스
    shared_data = {'frame': None, 'running': True}
    tts = TextToSpeech()
    depth_with_tts = DepthWithTTS(tts)
    yolo_detector = YOLODetector()
    flag_monitor = FlagMonitor(tts)  # 플래그 모니터 초기화

    return webcam_processor, shared_data, depth_with_tts, yolo_detector, tts, flag_monitor

async def cancel_all_tasks():
    """현재 실행 중인 모든 비동기 작업을 취소"""
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

async def main():
    # 구성 요소 초기화
    webcam_processor, shared_data, depth_with_tts, yolo_detector, tts, flag_monitor = initialize_components()

    print("Starting async processes...")

    # 플래그 확인 함수 생성
    detection_flag_func = lambda: yolo_detector.detection_flag
    catch_flag_func = lambda: flag_monitor.catch_flag  # HandDetection에서 관리하는 플래그

    # 플래그 모니터링 작업 생성
    flag_monitor_task = asyncio.create_task(flag_monitor.monitor_flags())

    # 프레임 공급 비동기 작업 생성
    frame_task = asyncio.create_task(webcam_processor.async_frame_provider(shared_data))

    # 개별 작업 비동기 실행
    depth_task = asyncio.create_task(depth_with_tts.run(shared_data))
    hand_task = asyncio.create_task(run_hand_detection(shared_data))
    yolo_task = asyncio.create_task(yolo_detector.run_detection(shared_data))

    try:
        while shared_data['running']:
            # `q` 키가 눌렸는지 확인
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("Terminating by user request (q key).")
                shared_data['running'] = False
                break
            await asyncio.sleep(0.1)  # 이벤트 루프 양보
    except KeyboardInterrupt:
        print("Terminating by KeyboardInterrupt.")
        shared_data['running'] = False  # 모든 작업 중단 신호
    finally:
        # 모든 작업 강제 취소
        print("Cancelling all tasks...")
        await cancel_all_tasks()

        # 자원 해제
        webcam_processor.release()
        cv2.destroyAllWindows()
        print("All resources released. Exiting program.")

if __name__ == "__main__":
    asyncio.run(main())
