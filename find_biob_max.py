"""
OpenMV 瑙嗚璇嗗埆鑴氭湰 - 鏀硅繘鐗?鍔熻兘锛氳瘑鍒粦鑹茶竟妗嗗唴鐨勭洰鏍囩墿浣擄紙鐭╁舰/鍦嗗舰/涓夎褰級锛屾祴璺濇祴灏哄锛屼覆鍙ｅ彂閫佹暟鎹?骞冲彴锛歄penMV (STM32/K210)
鏀硅繘鏃ユ湡锛?026-06-10

鏀硅繘鍐呭锛?- 淇 FRAME_HIGHT_MM 鎷煎啓閿欒 鈫?FRAME_HEIGHT_MM
- 绉婚櫎鏃犵敤甯搁噺 FRAME_HEIGHT_PIXEL_2
- CENTER_X / CENTER_Y 鏀逛负浠庡疄闄呯獥鍙ｅ昂瀵歌绠?- find_center_blob 鏀逛负缁熶竴鍑芥暟锛屾洿鍋ュ．鐨勫垵濮嬪寲閫昏緫
- 褰㈢姸璇嗗埆澧炲姞 area 鍜?w/h 姣斿€艰緟鍔╁垽鏂紝鍑忓皯璇瘑鍒?- 璺濈璁＄畻澧炲姞闄ら浂淇濇姢
- 鎻愬彇榄旀硶鏁板瓧鍒板父閲忥紝闆嗕腑绠＄悊闃堝€?- 澧炲姞 FPS 鏄剧ず
- 澧炲姞 debug 妯″紡寮€鍏?- 缁熶竴寮傚父鐘舵€佺殑鏁版嵁鍖呭彂閫?"""

import sensor
import time
from pyb import UART
import lcd

# ============================================================
# 鍏ㄥ眬寮€鍏?# ============================================================
DEBUG = True              # 璋冭瘯妯″紡锛歍rue 鎵撳嵃璇︾粏鏃ュ織锛孎alse 闈欓粯杩愯

# ============================================================
# 涓插彛鍒濆鍖?# ============================================================
UART_CHANNEL = 3          # UART 閫氶亾
UART_BAUD = 115200        # 娉㈢壒鐜?
lcd.init()
uart = UART(UART_CHANNEL, UART_BAUD)
uart.init(UART_BAUD, bits=8, parity=None, stop=1)

# ============================================================
# 鏁版嵁鍖呭崗璁畾涔?# ============================================================
PACKET_HEADER = 0xAA  # 鍖呭ご
PACKET_TAIL = 0x55    # 鍖呭熬

# 褰㈢姸缂栫爜
SHAPE_NONE = 0        # 鏈瘑鍒?SHAPE_RECTANGLE = 1   # 鐭╁舰
SHAPE_CIRCLE = 2      # 鍦嗗舰
SHAPE_TRIANGLE = 3    # 涓夎褰?
# 褰㈢姸鍚嶇О鏄犲皠
SHAPE_NAMES = {
    SHAPE_NONE: "鏈瘑鍒?,
    SHAPE_RECTANGLE: "鐭╁舰",
    SHAPE_CIRCLE: "鍦嗗舰",
    SHAPE_TRIANGLE: "涓夎褰?,
}

# ============================================================
# 鎽勫儚澶村垵濮嬪寲
# ============================================================
sensor.reset()
sensor.set_pixformat(sensor.GRAYSCALE)
sensor.set_framesize(sensor.VGA)        # 640x480
sensor.set_windowing((230, 300))        # 瑁佸壀涓棿 230x300 鍖哄煙
sensor.skip_frames(time=2000)
clock = time.clock()
sensor.set_vflip(1)
sensor.set_hmirror(1)
sensor.skip_frames(30)

# 璁＄畻鐢婚潰涓績锛堝熀浜庡疄闄呰鍓昂瀵革級
IMAGE_W, IMAGE_H = 230, 300
CENTER_X = IMAGE_W // 2
CENTER_Y = IMAGE_H // 2

# ============================================================
# 鏍″噯鍙傛暟
# ============================================================
# 杈规鐪熷疄灏哄 (mm)
FRAME_WIDTH_MM = 180
FRAME_HEIGHT_MM = 255

# 璺濈鏍″噯鐐癸細璺濈 2000mm 鏃讹紝杈规瀹藉害涓?89 鍍忕礌
# 渚嬪锛氬綋璺濈鏄?1100mm 鏃讹紝杈规瀹藉害涓?104 鍍忕礌
DISTANCE_CAL_MM = 2000
FRAME_WIDTH_CAL_PX = 89

# ============================================================
# 鍥惧儚澶勭悊闃堝€?# ============================================================
# 鑹插潡鎼滅储鐏板害鑼冨洿
WHITE_THRESHOLD = (150, 256)    # 鐧借壊锛堣竟妗嗗唴閮級
BLACK_THRESHOLD = (0, 150)      # 榛戣壊锛堢洰鏍囩墿浣擄級
# 娉細鍙崟鐙皟鏁寸洰鏍囩墿浣撻槇鍊硷紝渚嬪 (0, 80) 浠呰瘑鍒繁榛戣壊鐗╀綋

# 涓績鍋忕Щ瀹瑰繊搴︼紙璺濅腑蹇?Manhattan 璺濈涓婇檺锛屽儚绱狅級
CENTER_TOLERANCE = 50

# 鏈€灏忚壊鍧楅潰绉紙婊ゆ尝鍣０锛?MIN_BLOB_AREA = 20

# ROI 鏀剁缉閲忥紙鍘婚櫎榛戞榛戣竟锛屽儚绱狅級
ROI_SHRINK_X = 5
ROI_SHRINK_Y = 5
ROI_SHRINK_W = 10   # 鎬绘敹缂╁搴?= shrink_x * 2
ROI_SHRINK_H = 10   # 鎬绘敹缂╅珮搴?= shrink_y * 2

# 褰㈢姸璇嗗埆闃堝€?DENSITY_RECT = 0.90   # density > 姝ゅ€?鈫?鐭╁舰
DENSITY_CIRC = 0.60   # density > 姝ゅ€?鈫?鍦嗗舰锛堜笖 鈮?RECT锛?DENSITY_TRI = 0.40    # density > 姝ゅ€?鈫?涓夎褰紙涓?鈮?CIRC锛?# 杈呭姪锛氬楂樻瘮鐢ㄤ簬鍖哄垎鐭╁舰鍜屽渾褰?ASPECT_RATIO_RECT_MIN = 0.70   # 鐭╁舰 w/h 鑷冲皯灏忎簬姝ゅ€硷紙瓒婄獎瓒婂儚鐭╁舰锛?ASPECT_RATIO_RECT_MAX = 1.30

# 涓诲惊鐜欢鏃?(ms)
LOOP_DELAY_MS = 500

# ============================================================
# 杈呭姪鍑芥暟
# ============================================================

def find_center_blob(blobs, mode="max"):
    """
    鍦ㄧ敾闈腑蹇冨尯鍩熷唴鎵捐壊鍧椼€?    mode: "max" 鎵炬渶澶? "min" 鎵炬渶灏?    杩斿洖鎵惧埌鐨?blob 鎴?None
    """
    if not blobs:
        return None

    best_blob = None
    if mode == "max":
        best_value = -1
    else:
        best_value = float('inf')

    for b in blobs:
        # 杩囨护涓績鍖哄煙浠ュ鐨勮壊鍧?        if abs(b.cx() - CENTER_X) + abs(b.cy() - CENTER_Y) > CENTER_TOLERANCE:
            continue
        # 杩囨护杩囧皬鐨勫櫔鐐?        if b.area() < MIN_BLOB_AREA:
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
    鏍规嵁杈规鍍忕礌瀹藉害璁＄畻璺濈 (mm)銆?    鍩轰簬鐩镐技涓夎褰㈠師鐞嗭細distance 鈭?1/width
    杩斿洖 NaN 琛ㄧず鏃犳晥娴嬮噺
    """
    if frame_width_px <= 0:
        return float('nan')
    return DISTANCE_CAL_MM * FRAME_WIDTH_CAL_PX / frame_width_px


def calc_object_size_mm(obj_px, frame_px):
    """鏍规嵁鐗╀綋鍍忕礌/杈规鍍忕礌姣斾緥璁＄畻鐗╀綋瀹為檯灏哄 (mm)"""
    if frame_px <= 0:
        return 0.0
    return obj_px / frame_px * FRAME_WIDTH_MM


def classify_shape(blob):
    """
    鍩轰簬 density锛堝瘑瀹炲害 = area / bounding_box_area锛夊拰
    w/h 姣斿€煎垽鏂舰鐘躲€?    杩斿洖 (shape_code, shape_name)
    """
    density = blob.density()

    # 榛樿鏈煡褰㈢姸
    shape_code = SHAPE_NONE

    if density > DENSITY_RECT:
        shape_code = SHAPE_RECTANGLE
    elif density > DENSITY_CIRC:
        # 杈呭姪鍒ゆ柇锛氬渾褰?w/h 鎺ヨ繎 1:1
        w, h = blob.w(), blob.h()
        ratio = w / h if h > 0 else 0
        if ASPECT_RATIO_RECT_MIN < ratio < ASPECT_RATIO_RECT_MAX:
            shape_code = SHAPE_CIRCLE
        else:
            # 瀵嗗害鎺ヨ繎鐭╁舰浣?w/h 涓嶆帴杩?1 鈫?鏇村彲鑳芥槸鐭╁舰鏉?            shape_code = SHAPE_RECTANGLE
    elif density > DENSITY_TRI:
        shape_code = SHAPE_TRIANGLE

    return shape_code, SHAPE_NAMES[shape_code]


def send_packet(shape_code, distance_mm, length_mm):
    """
    閫氳繃涓插彛鍙戦€佹暟鎹寘銆?    鍗忚锛歔0xAA] [shape_code] [distance_H] [distance_L] [length_H] [length_L] [0x55]
    distance 鍜?length 浠?1 浣嶅皬鏁扮簿搴︾紪鐮侊紙鍊?* 10 鍚庢媶涓?2 瀛楄妭澶х锛?    """
    try:
        # 娴偣 鈫?鏁存暟锛堜繚鐣?1 浣嶅皬鏁帮級
        dist_int = int(round(distance_mm * 10))
        len_int = int(round(length_mm * 10))

        # 闄愬箙锛岄槻姝㈡孩鍑?        dist_int = max(0, min(65535, dist_int))
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
        print("涓插彛鍙戦€侀敊璇? %s" % e)


def draw_overlay(img, frame_blob, obj_blob, shape_name, distance, obj_size):
    """鍦ㄥ浘鍍忎笂缁樺埗妫€娴嬬粨鏋滃拰杈圭晫妗?""
    # 杈规妗?    if frame_blob:
        img.draw_rectangle(frame_blob.rect(), color=255, thickness=2)
    # 鐗╀綋妗?    if obj_blob:
        img.draw_rectangle(obj_blob.rect(), color=0, thickness=2)

    # 淇℃伅鍙犲姞
    img.draw_string(10, 10, "shape:%s" % shape_name)
    img.draw_string(10, 22, "dist:%.0fmm" % distance)
    img.draw_string(10, 34, "size:%.0fmm" % obj_size)

    # 涓績鍗佸瓧
    img.draw_cross(CENTER_X, CENTER_Y, color=128, size=5)

# ============================================================
# 涓诲惊鐜?# ============================================================

while True:
    clock.tick()
    img = sensor.snapshot()

    # --------------------------------------------------------
    # 1. 鎵剧櫧鑹插尯鍩?鈫?璇嗗埆榛戣壊杈规
    # --------------------------------------------------------
    frames = img.find_blobs([WHITE_THRESHOLD])
    frame_blob = find_center_blob(frames, mode="min")  # 鎵炬渶灏忕殑鐧借壊鍧?= 杈规鍐呴儴

    if not frame_blob:
        print("NO FRAME")
        send_packet(SHAPE_NONE, 0, 0)
        img.draw_string(50, CENTER_Y, "NO FRAME")
        lcd.display(img)
        continue

    # --------------------------------------------------------
    # 2. 璁＄畻璺濈
    # --------------------------------------------------------
    distance = calc_distance(frame_blob.w())
    if distance != distance:  # NaN 妫€鏌?        print("DISTANCE ERROR: frame_w=%d" % frame_blob.w())
        send_packet(SHAPE_NONE, 0, 0)
        continue

    # --------------------------------------------------------
    # 3. 鏀剁缉 ROI锛堟帓闄ら粦妗嗙殑榛戣竟锛?    # --------------------------------------------------------
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
    # 4. 鎵鹃粦鑹茶壊鍧?鈫?鐩爣鐗╀綋
    # --------------------------------------------------------
    objs = img.find_blobs([BLACK_THRESHOLD], roi=(roi_x, roi_y, roi_w, roi_h))
    obj_blob = find_center_blob(objs, mode="max")  # 鎵炬渶澶х殑榛戣壊鍧?
    if not obj_blob:
        print("NO OBJECT")
        send_packet(SHAPE_NONE, distance, 0)
        draw_overlay(img, frame_blob, None, "none", distance, 0)
        lcd.display(img)
        continue

    # --------------------------------------------------------
    # 5. 璁＄畻鐗╀綋灏哄 & 鍒嗙被褰㈢姸
    # --------------------------------------------------------
    obj_size_mm = calc_object_size_mm(obj_blob.w(), frame_blob.w())
    shape_code, shape_name = classify_shape(obj_blob)

    if DEBUG:
        fps = clock.fps()
        print("FPS:%.1f | %s dist=%.0fmm size=%.0fmm dens=%.3f"
              % (fps, shape_name, distance, obj_size_mm, obj_blob.density()))

    # --------------------------------------------------------
    # 6. 涓插彛鍙戦€?鈫?鏄剧ず
    # --------------------------------------------------------
    send_packet(shape_code, distance, obj_size_mm)
    draw_overlay(img, frame_blob, obj_blob, shape_name, distance, obj_size_mm)
    lcd.display(img)

    time.sleep_ms(LOOP_DELAY_MS)
