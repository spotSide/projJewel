import cv2
import numpy as np
import openvino as ov
from pathlib import Path
import asyncio
import matplotlib.cm
import random
import sys
import os

# 유틸리티 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
utils_dir = os.path.join(parent_dir, "utils")
sys.path.append(utils_dir)
import notebook_utils as utils


class DepthProcessor:
    def __init__(self, compiled_model, input_key, output_key):
        self.compiled_model = compiled_model
        self.input_key = input_key
        self.output_key = output_key

    def process_frame(self, frame):
        """주어진 프레임에서 뎁스 결과를 생성합니다."""
        resized_frame = cv2.resize(frame, (self.input_key.shape[2], self.input_key.shape[3]))
        input_image = np.expand_dims(np.transpose(resized_frame, (2, 0, 1)), 0)
        result = self.compiled_model([input_image])[self.output_key]
        return result

    def visualize_result(self, result):
        """뎁스 결과를 시각화합니다."""
        result_frame = self.convert_result_to_image(result)
        return result_frame

    @staticmethod
    def normalize_minmax(data):
        """뎁스 데이터를 정규화합니다."""
        return (data - data.min()) / (data.max() - data.min())

    def convert_result_to_image(self, result, colormap="viridis"):
        """뎁스 결과를 컬러맵으로 변환합니다."""
        cmap = matplotlib.colormaps[colormap]
        result = result.squeeze(0)
        result = self.normalize_minmax(result)
        result = cmap(result)[:, :, :3] * 255
        result = result.astype(np.uint8)
        return result


def process_depth_sections(depth_map, num_rows=5, num_cols=5, threshold=0.85):
    """깊이 맵을 섹션으로 나누고, 각 섹션의 평균 뎁스를 계산하여 방향을 결정합니다."""
    h, w = depth_map.shape
    section_height = h // num_rows
    section_width = w // num_cols
    
    left_count = 0
    right_count = 0
    threshold_hit = False  # 쓰레스홀드를 만족하는 섹션이 있는지 확인

    for row in range(num_rows):
        for col in range(num_cols):
            y1, y2 = row * section_height, (row + 1) * section_height
            x1, x2 = col * section_width, (col + 1) * section_width
            section = depth_map[y1:y2, x1:x2]
            mean_depth = section.mean()
            
            if mean_depth >= threshold:
                threshold_hit = True
                if col < num_cols // 2:
                    left_count += 1
                else:
                    right_count += 1

    if not threshold_hit:  # Threshold를 만족하는 섹션이 없으면 None 반환
        return None

    if left_count > right_count:
        return "Avoid to Right"
    elif right_count > left_count:
        return "Avoid to Left"
    else:
        return random.choice(["Avoid to Right", "Avoid to Left"])


def display_depth_sections(image, depth_map, num_rows=5, num_cols=5, output_width=1280, output_height=720):
    """깊이 맵 섹션을 표시하고 평균 뎁스를 시각화합니다."""
    image = cv2.resize(image, (output_width, output_height))
    depth_map = cv2.resize(depth_map, (output_width, output_height))

    section_height = output_height // num_rows
    section_width = output_width // num_cols

    for row in range(num_rows):
        for col in range(num_cols):
            y1, y2 = row * section_height, (row + 1) * section_height
            x1, x2 = col * section_width, (col + 1) * section_width
            section = depth_map[y1:y2, x1:x2]
            mean_depth = section.mean()

            cv2.putText(
                image,
                f"{mean_depth:.2f}",
                (x1 + 10, y1 + 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
                cv2.LINE_AA
            )
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 1)

    return image


def download_midas_model():
    """MiDaS 모델 다운로드 및 설정"""
    model_folder = Path("model/midas")
    model_folder.mkdir(parents=True, exist_ok=True)

    ir_model_url = "https://storage.openvinotoolkit.org/repositories/openvino_notebooks/models/depth-estimation-midas/FP32/"
    ir_model_name_xml = "MiDaS_small.xml"
    ir_model_name_bin = "MiDaS_small.bin"

    if not (model_folder / ir_model_name_xml).exists():
        utils.download_file(ir_model_url + ir_model_name_xml, filename=ir_model_name_xml, directory=model_folder)
    if not (model_folder / ir_model_name_bin).exists():
        utils.download_file(ir_model_url + ir_model_name_bin, filename=ir_model_name_bin, directory=model_folder)

    model_xml_path = model_folder / ir_model_name_xml
    print(f"MiDaS model downloaded at: {model_xml_path}")
    return model_xml_path


async def unified_depth(shared_data):
    """비동기적으로 뎁스 모델을 실행하고 섹션 분석 및 시각화를 수행합니다."""
    depth_processor = setup_depth_model()
    
    while shared_data['running']:
        frame = shared_data.get('frame')
        if frame is None:
            await asyncio.sleep(0)  # 이벤트 루프 양보
            continue

        try:
            depth_result = depth_processor.process_frame(frame)
            depth_map = (depth_result.squeeze(0) - depth_result.min()) / (depth_result.max() - depth_result.min())
            depth_frame = depth_processor.visualize_result(depth_result)

            decision = process_depth_sections(depth_map, num_rows=5, num_cols=5, threshold=0.85)

            if decision:  # Threshold 충족 시에만 실행
                depth_frame_with_sections = display_depth_sections(
                    depth_frame.copy(), depth_map, num_rows=5, num_cols=5, output_width=1280, output_height=720
                )

                cv2.putText(
                    depth_frame_with_sections,
                    decision,
                    (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA
                )

                cv2.imshow("Depth Estimation", depth_frame_with_sections)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                shared_data['running'] = False
                break

        except Exception as e:
            print(f"Error in unified_depth: {e}")
            shared_data['running'] = False
            break

        await asyncio.sleep(0)


def setup_depth_model():
    core = ov.Core()
    model_path = download_midas_model()
    model = core.read_model(model_path)
    compiled_model = core.compile_model(model=model, device_name="GPU")
    input_key = compiled_model.input(0)
    output_key = compiled_model.output(0)
    return DepthProcessor(compiled_model, input_key, output_key)
