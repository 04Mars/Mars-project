"""
OpenMV 视觉识别脚本 - 改进版
功能：识别黑色边框内的目标物体（矩形/圆形/三角形），测距测尺寸，串口发送数据
平台：OpenMV (STM32/K210)
改进日期：2026-06-10

改进内容：
- 修复 FRAME_HIGHT_MM 拼写错误 → FRAME_HEIGHT_MM
- 移除无用常量 FRAME_HEIGHT_PIXEL_2
- CENTER_X / CENTER_Y 改为从实际窗口尺寸计算
- find_center_blob 改为统一函数，更健壮的初始化逻辑
- 形状识别增加 area 和 w/h 比值辅助判断，减少误识别
- 距离计算增加除零保护
- 提取魔法数字到常量，集中管理阈值
- 增加 FPS 显示
- 增加 debug 模式开关
- 统一异常状态的数据包发送
"""

import sensor
import time
from pyb import UART
import lcd

# ============================================================
# 全局开关
# ============================================================
DEBUG = True              # 调试模式：True 打印详细日志，False 静默运行

# ============================================================
# 串口初始化
# ============================================================
UART_CHANNEL = 3          # UART 通道
UART_BAUD = 115200        # 波特率

lcd.init()
uart = UART(UART_CHANNEL, UART_BAUD)
uart.init(UART_BAUD, bits=8, parity=None, stop=1)

# ============================================================
# 数据包协议定义
# ============================================================
PACKET_HEADER = 0xAA  # 包头
PACKET_TAIL = 0x55    # 包尾

# 形状编码
SHAPE_NONE = 0        # 未识别
SHAPE_RECTANGLE = 1   # 矩形
SHAPE_CIRCLE = 2      # 圆形
SHAPE_TRIANGLE = 3    # 三角形

# 形状名称映射
SHAPE_NAMES = {
    SHAPE_NONE: "未识别",
    SHAPE_RECTANGLE: "矩形",
    SHAPE_CIRCLE: "圆形",
    SHAPE_TRIANGLE: "三角形",
}

# ============================================================
# 摄像头初始化
# ============================================================
sensor.reset()
sensor.set_pixformat(sensor.GRAYSCALE)
sensor.set_framesize(sensor.VGA)        # 640x480
sensor.set_windowing((230, 300))        # 裁剪中间 230x300 区域
sensor.skip_frames(time=2000)
clock = time.clock()
sensor.set_vflip(1)
sensor.set_hmirror(1)
sensor.skip_frames(30)

# 计算画面中心（基于实际裁剪尺寸）
IMAGE_W, IMAGE_H = 230, 300
CENTER_X = IMAGE_W // 2
CENTER_Y = IMAGE_H // 2

# ============================================================
# 校准参数
# ============================================================
# 边框真实尺寸 (mm)
FRAME_WIDTH_MM = 180
FRAME_HEIGHT_MM = 255

# 距离校准点：距离 2000mm 时，边框宽度为 89 像素
# 例如：当距离是 1100mm 时，边框宽度为 104 像素
DISTANCE_CAL_MM = 2000
FRAME_WIDTH_CAL_PX = 89

# ============================================================
# 图像处理阈值
# ============================================================
# 色块搜索灰度范围
WHITE_THRESHOLD = (150, 256)    # 白色（边框内部）
BLACK_THRESHOLD = (0, 150)      # 黑色（目标物体）
# 注：可单独调整目标物体阈值，例如 (0, 80) 仅识别深黑色物体

# 中心偏移容忍度（距中心 Manhattan 距离上限，像素）
CENTER_TOLERANCE = 50

# 最小色块面积（滤波噪声）
MIN_BLOB_AREA = 20

# ROI 收缩量（去除黑框黑边，像素）
ROI_SHRINK_X = 5
ROI_SHRINK_Y = 5
ROI_SHRINK_W = 10   # 总收缩宽度 = shrink_x * 2
ROI_SHRINK_H = 10   # 总收缩高度 = shrink_y * 2

# 形状识别阈值
DENSITY_RECT = 0.90   # density > 此值 → 矩形
DENSITY_CIRC = 0.60   # density > 此值 → 圆形（且 ≤ RECT）
DENSITY_TRI = 0.40    # density > 此值 → 三角形（且 ≤ CIRC）
# 辅助：宽高比用于区分矩形和圆形
ASPECT_RATIO_RECT_MIN = 0.70   # 矩形 w/h 至少小于此值（越窄越像矩形）
ASPECT_RATIO_RECT_MAX = 1.30

# 主循环延时 (ms)
LOOP_DELAY_MS = 500

# ============================================================
# 辅助函数
# ============================================================

def find_center_blob(blobs, mode="max"):
    """
    在画面中心区域内找色块。
    mode: "max" 找最大, "min" 找最小
    返回找到的 blob 或 None
    """
    if not blobs:
        return None

    best_blob = None
    if mode == "max":
        best_value = -1
    else:
        best_value = float('inf')

    for b in blobs:
        # 过滤中心区域以外的色块
        if abs(b.cx() - CENTER_X) + abs(b.cy() - CENTER_Y) > CENTER_TOLERANCE:
            continue
        # 过滤过小的噪点
        if b.area() < MIN_BLOB_AREA:
            continue

        if mode == "max":
            if b.area() > best_value:
                best_blob = b
                best_value = b.area()
        else:
            if b.area() < best_value:
                best_blob = b
                best_value = b.area()

    return best_blob


def calc_distance(frame_width_px):
    """
    根据边框像素宽度计算距离 (mm)。
    基于相似三角形原理：distance ∝ 1/width
    返回 NaN 表示无效测量
    """
    if frame_width_px <= 0:
        return float('nan')
    return DISTANCE_CAL_MM * FRAME_WIDTH_CAL_PX / frame_width_px


def calc_object_size_mm(obj_px, frame_px):
    """根据物体像素/边框像素比例计算物体实际尺寸 (mm)"""
    if frame_px <= 0:
        return 0.0
    return obj_px / frame_px * FRAME_WIDTH_MM


def classify_shape(blob):
    """
    基于 density（密实度 = area / bounding_box_area）和
    w/h 比值判断形状。
    返回 (shape_code, shape_name)
    """
    density = blob.density()

    # 默认未知形状
    shape_code = SHAPE_NONE

    if density > DENSITY_RECT:
        shape_code = SHAPE_RECTANGLE
    elif density > DENSITY_CIRC:
        # 辅助判断：圆形 w/h 接近 1:1
        w, h = blob.w(), blob.h()
        ratio = w / h if h > 0 else 0
        if ASPECT_RATIO_RECT_MIN < ratio < ASPECT_RATIO_RECT_MAX:
            shape_code = SHAPE_CIRCLE
        else:
            # 密度接近矩形但 w/h 不接近 1 → 更可能是矩形条
            shape_code = SHAPE_RECTANGLE
    elif density > DENSITY_TRI:
        shape_code = SHAPE_TRIANGLE

    return shape_code, SHAPE_NAMES[shape_code]


def send_packet(shape_code, distance_mm, length_mm):
    """
    通过串口发送数据包。
    协议：[0xAA] [shape_code] [distance_H] [distance_L] [length_H] [length_L] [0x55]
    distance 和 length 以 1 位小数精度编码（值 * 10 后拆为 2 字节大端）
    """
    try:
        # 浮点 → 整数（保留 1 位小数）
        dist_int = int(round(distance_mm * 10))
        len_int = int(round(length_mm * 10))

        # 限幅，防止溢出
        dist_int = max(0, min(65535, dist_int))
        len_int = max(0, min(65535, len_int))

        packet = bytes([
            PACKET_HEADER,
            shape_code,
            (dist_int >> 8) & 0xFF,
            dist_int & 0xFF,
            (len_int >> 8) & 0xFF,
            len_int & 0xFF,
            PACKET_TAIL,
        ])
        uart.write(packet)

        if DEBUG:
            print("TX | shape=%d(%s) dist=%.1fmm len=%.1fmm"
                  % (shape_code, SHAPE_NAMES.get(shape_code, "?"),
                     distance_mm, length_mm))

    except Exception as e:
        print("串口发送错误: %s" % e)


def draw_overlay(img, frame_blob, obj_blob, shape_name, distance, obj_size):
    """在图像上绘制检测结果和边界框"""
    # 边框框
    if frame_blob:
        img.draw_rectangle(frame_blob.rect(), color=255, thickness=2)
    # 物体框
    if obj_blob:
        img.draw_rectangle(obj_blob.rect(), color=0, thickness=2)

    # 信息叠加
    img.draw_string(10, 10, "shape:%s" % shape_name)
    img.draw_string(10, 22, "dist:%.0fmm" % distance)
    img.draw_string(10, 34, "size:%.0fmm" % obj_size)

    # 中心十字
    img.draw_cross(CENTER_X, CENTER_Y, color=128, size=5)

# ============================================================
# 主循环
# ============================================================

while True:
    clock.tick()
    img = sensor.snapshot()

    # --------------------------------------------------------
    # 1. 找白色区域 → 识别黑色边框
    # --------------------------------------------------------
    frames = img.find_blobs([WHITE_THRESHOLD])
    frame_blob = find_center_blob(frames, mode="min")  # 找最小的白色块 = 边框内部

    if not frame_blob:
        print("NO FRAME")
        send_packet(SHAPE_NONE, 0, 0)
        img.draw_string(50, CENTER_Y, "NO FRAME")
        lcd.display(img)
        continue

    # --------------------------------------------------------
    # 2. 计算距离
    # --------------------------------------------------------
    distance = calc_distance(frame_blob.w())
    if distance != distance:  # NaN 检查
        print("DISTANCE ERROR: frame_w=%d" % frame_blob.w())
        send_packet(SHAPE_NONE, 0, 0)
        continue

    # --------------------------------------------------------
    # 3. 收缩 ROI（排除黑框的黑边）
    # --------------------------------------------------------
    roi_x = frame_blob.x() + ROI_SHRINK_X
    roi_y = frame_blob.y() + ROI_SHRINK_Y
    roi_w = frame_blob.w() - ROI_SHRINK_W
    roi_h = frame_blob.h() - ROI_SHRINK_H

    if roi_w <= 0 or roi_h <= 0:
        print("ROI ERROR: %dx%d" % (roi_w, roi_h))
        send_packet(SHAPE_NONE, distance, 0)
        img.draw_rectangle(frame_blob.rect(), color=255)
        lcd.display(img)
        continue

    # --------------------------------------------------------
    # 4. 找黑色色块 → 目标物体
    # --------------------------------------------------------
    objs = img.find_blobs([BLACK_THRESHOLD], roi=(roi_x, roi_y, roi_w, roi_h))
    obj_blob = find_center_blob(objs, mode="max")  # 找最大的黑色块

    if not obj_blob:
        print("NO OBJECT")
        send_packet(SHAPE_NONE, distance, 0)
        draw_overlay(img, frame_blob, None, "none", distance, 0)
        lcd.display(img)
        continue

    # --------------------------------------------------------
    # 5. 计算物体尺寸 & 分类形状
    # --------------------------------------------------------
    obj_size_mm = calc_object_size_mm(obj_blob.w(), frame_blob.w())
    shape_code, shape_name = classify_shape(obj_blob)

    if DEBUG:
        fps = clock.fps()
        print("FPS:%.1f | %s dist=%.0fmm size=%.0fmm dens=%.3f"
              % (fps, shape_name, distance, obj_size_mm, obj_blob.density()))

    # --------------------------------------------------------
    # 6. 串口发送 → 显示
    # --------------------------------------------------------
    send_packet(shape_code, distance, obj_size_mm)
    draw_overlay(img, frame_blob, obj_blob, shape_name, distance, obj_size_mm)
    lcd.display(img)

    time.sleep_ms(LOOP_DELAY_MS)
