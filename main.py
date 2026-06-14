# -*- coding: utf-8 -*-
"""
本代码实现了一个自学习应用，用于对摄像头采集的图像进行模型推理、特征采集及后续特征匹配
This code implements a self-learning application for performing model inference on frames captured by a sensor,
feature collection, and subsequent feature matching.
"""
from media.display import *
# 导入依赖的库和模块
# Import necessary libraries and modules
from libs.PipeLine import PipeLine, ScopedTiming  # Pipeline和计时工具 // pipeline and timing tool
from libs.AIBase import AIBase  # 基础的AI类 // the base AI class
from libs.AI2D import Ai2d  # 用于图像预处理的Ai2d模块 // Ai2d module for image preprocessing
import os  # 操作系统接口 // operating system interfaces
import ujson  # 快速JSON解析 // fast JSON parsing
from media.media import *  # 媒体处理模块 // media processing module
from time import *  # 时间模块 // time module
import nncase_runtime as nn  # nncase运行时 // nncase runtime module
import ulab.numpy as np  # ulab下的numpy，用于嵌入式数值计算 // ulab numpy for embedded numerical computation
import time  # 标准时间模块 // standard time module
import utime  # 微型嵌入式时间模块 // micro-time module for embedded systems
import image  # 图像处理模块 // image processing module
import random  # 随机数模块 // random number module
import gc  # 垃圾回收模块 // garbage collection module
import sys  # 系统模块 // system-specific parameters and functions
import aicube  # aicube模块, 可用于AI算子 // aicube module, can be used for AI operators

from libs.YbProtocol import YbProtocol
from ybUtils.YbUart import YbUart

import _thread
import os
from media.media import *
from media.pyaudio import *
from media.sensor import Sensor
import media.wave as wave
import time
from ybUtils.YbKey import YbKey
import ybUtils.YbRequests as urequests
import YbRequests as requests2
import os, time, gc
from ybUtils.YbSpeaker import YbSpeaker
from ybUtils.YbBuzzer import YbBuzzer
from ybUtils.YbRGB import YbRGB
import re

# ============================================================
# DashScope 配置 (独立运行: 替换笔记本服务器)
# ============================================================
WIFI_SSID = "11111"
WIFI_KEY = "88888888"
API_KEY = "sk-7f1f0e35b05d44239b6eefa43cff1996"

# ============================================================

# ============================================================
REGISTER_MODE = False  # True=注册药盒, 注册完成后改为False
GEN_WAV = False         # True=联网生成一次播报WAV文件, 完成后改为False

# ============================================================
# 药品信息字典 — 本地识别到药盒后直接查字典播报(快速路径)
# key: 必须与 labels 中的名称一致
# ============================================================
MEDICINE_INFO = {
    "阿莫西林": "阿莫西林胶囊，用于细菌呼吸道、泌尿感染消炎。成人1次2粒，一日3次，饭后服。青霉素过敏禁用，肾衰老人减量。起红疹、胸闷立即停药就医。",
    "诺氟沙星": "诺氟沙星胶囊，用于细菌性腹泻、尿路感染。尿路感染1次4粒一日2次，肠炎1次3粒一日2次，空腹多喝水。高龄肾病慎用，18岁以下禁用。",
    "感康": "复方氨酚烷胺片，用于感冒发烧、鼻塞头痛。1次1片，一日2次。禁酒，不与其他感冒药同服，服药易犯困防跌倒。",
}

SAMPLE_RATE = 16000         # 采样率 24000Hz，即每秒采样24000次 / Sample rate 24000Hz, i.e., 24000 samples per second
CHANNELS = 1                # 通道数，1为单声道 / Number of channels, 1 for mono
FORMAT = paInt16            # 音频输入输出格式 / Audio input/output format
CHUNK = int(0.3 * 24000)    # 每次读取音频数据的帧数，设置为0.3秒的帧数 / Number of frames to read each time, set to 0.3 seconds of frames
# 初始化音频流 / Initialize audio stream
rgb = YbRGB()
buzzer = YbBuzzer()
# uart = None

screen_width = 640
screen_height = 480

banner_width = screen_width
banner_height = 100

banner_x = (screen_width - banner_width) // 2
banner_y = 0

def connect_wifi():
    print("Connecting to WiFi...")
    import network
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        print(f"WiFi already, IP: {wlan.ifconfig()[0]}")
        rgb.show_rgb((0, 255, 0))
        return True
    wlan.connect(WIFI_SSID, WIFI_KEY)
    timeout = 15
    while not wlan.isconnected() and timeout > 0:
        time.sleep(1)
        timeout -= 1
        print(f"  waiting... {timeout}s")
    if wlan.isconnected():
        print(f"WiFi connected, IP: {wlan.ifconfig()[0]}")
        rgb.show_rgb((0, 255, 0))
        return True
    print("WiFi timeout!")
    return False

def network_use_wlan(ssid, key):
    # 保留旧接口兼容
    return connect_wifi()

class AudioRecorder:
    """
    音频录制类
    Audio recorder class
    """
    def __init__(self):
        """
        初始化音频参数
        Initialize audio parameters
        """
        self.FORMAT = paInt16       # 采样格式为16位整型 / 16-bit integer sampling format
        self.CHANNELS = 1           # 单声道 / Mono channel
        self.RATE = 16000
        self.CHUNK = self.RATE // 25    # 每个缓冲区的帧数 / Frames per buffer
        self.frames = []            # 存储录音帧 / Store recorded frames
        self.is_recording = False   # 录音状态标志 / Recording status flag

        # 初始化PyAudio / Initialize PyAudio
        self.p = PyAudio()
        self.p.initialize(self.CHUNK)
#        MediaManager.init()

    def exit_check(self):
        """
        检查是否有退出信号
        Check if there is an exit signal
        """
        try:
            os.exitpoint()
        except KeyboardInterrupt as e:
            print("user stop: ", e)
            return True
        return False

    def record_with_button(self, filename, key, left_volume=85, right_volume=85, ans=False):
        """
        按键控制录制音频
        Record audio with button control

        参数 / Parameters:
            filename: 音频保存路径 / Path to save audio file
            key: 按键对象 / Button object
            left_volume: 左声道音量 / Left channel volume
            right_volume: 右声道音量 / Right channel volume
            ans: 是否启用音频3A功能：自动噪声抑制(ANS) / Open Ans or not
        """
        try:
            # 打开音频输入流 / Open audio input stream
            self.input_stream = self.p.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK
            )

            # 设置音量 / Set volume
            self.input_stream.volume(LEFT, left_volume)
            self.input_stream.volume(RIGHT, right_volume)

            if(ans):
                self.input_stream.enable_audio3a(AUDIO_3A_ENABLE_ANS)

            print("初始化完成，等待按键开始录制...")

            # 等待按键按下开始录制
            while not key.is_pressed():
                if self.exit_check():
                    return
                time.sleep(0.01)

            print("开始录制...按键松开时停止")
            self.frames = []
            self.is_recording = True
            img2 = image.Image(640, 480, image.RGB565)
            img2.clear()

            alert_text = "正在倾听... | Listening"
            text_x = (screen_width - len(alert_text) * 8) // 2  # 8 是字符宽度
            text_y = banner_y + (banner_height - 10) // 2  # 10 是字符高度
            img2.draw_string_advanced(text_x, text_y,18, alert_text, color=(255, 255, 255))

            Display.show_image(img2, 0, 0, Display.LAYER_OSD3)
            # 按住录制，松开停止
            while key.is_pressed() and self.is_recording:
                if self.exit_check():
                    break
                data = self.input_stream.read()
                self.frames.append(data)

            print("停止录制...")
            img2.clear()
            Display.show_image(img2, 0, 0, Display.LAYER_OSD3)
            # 保存为WAV文件 / Save as WAV file
            self._save_to_wav(filename)

        except BaseException as e:
            print(f"Exception {e}")
        finally:
            self.stop()

    def record(self, filename, duration, left_volume=85, right_volume=85, ans=False):
        """
        录制固定时长音频
        Record audio with fixed duration

        参数 / Parameters:
            filename: 音频保存路径 / Path to save audio file
            duration: 录制时长(秒) / Recording duration in seconds
            left_volume: 左声道音量 / Left channel volume
            right_volume: 右声道音量 / Right channel volume
            ans: 是否启用音频3A功能：自动噪声抑制(ANS) / Open Ans or not
        """
        try:
            # 打开音频输入流 / Open audio input stream
            self.input_stream = self.p.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK
            )

            # 设置音量 / Set volume
            self.input_stream.volume(LEFT, left_volume)
            self.input_stream.volume(RIGHT, right_volume)

            if(ans):
                self.input_stream.enable_audio3a(AUDIO_3A_ENABLE_ANS)
            buzzer.on(1000, 5, 0.3)
            print("start record...")

            self.frames = []
            self.is_recording = True

            # 开始录制 / Start recording
            for i in range(0, int(self.RATE / self.CHUNK * duration)):
                if not self.is_recording or self.exit_check():
                    break
                data = self.input_stream.read()
                self.frames.append(data)
                time.sleep_us(1)

            print("stop record...")
            buzzer.on(2500, 5, 0.3)
            # 保存为WAV文件 / Save as WAV file
            self._save_to_wav(filename)

        except BaseException as e:
            print(f"Exception {e}")
        finally:
            self.stop()

    def stop(self):
        """
        停止录音并清理资源
        Stop recording and cleanup resources
        """
        self.is_recording = False
        if hasattr(self, 'input_stream'):
            self.input_stream.stop_stream()
            self.input_stream.close()
#        self.p.terminate()
#        MediaManager.deinit()

    def _save_to_wav(self, filename):
        """
        保存录音为WAV文件
        Save recording as WAV file

        参数 / Parameters:
            filename: 保存路径 / Save path
        """
        if not self.frames:  # 如果没有录到任何帧，就不保存文件
            print("没有录制到任何音频，不保存文件")
            return

        wf = wave.open(filename, 'wb')
        wf.set_channels(self.CHANNELS)
        wf.set_sampwidth(self.p.get_sample_size(self.FORMAT))
        wf.set_framerate(self.RATE)
        wf.write_frames(b''.join(self.frames))
        wf.close()
        print(f"录音已保存到: {filename}")

    def play_audio(self,path):
        try:

            # 用于播放音频 / For playing audio
            output_stream = self.p.open(format=FORMAT, channels=CHANNELS, rate=SAMPLE_RATE, output=True, frames_per_buffer=self.CHUNK)
            output_stream.volume(vol=100)
            wf = wave.open(path, "rb")  # 打开WAV文件 / Open WAV file
            wav_data = wf.read_frames(self.CHUNK)          # 读取音频数据 / Read audio data
            while wav_data:
                output_stream.write(wav_data)         # 写入音频流播放 / Write to audio stream for playback
                wav_data = wf.read_frames(self.CHUNK)      # 继续读取下一段数据 / Continue reading the next segment of data
            time.sleep(2)  # 时间缓冲，用于播放声音 / Time buffer for playing sound
            wf.close()
        except Exception as e:
            print(e)
        finally:
            output_stream.stop_stream()
            output_stream.close()


def ensure_dir(directory):
    """
    递归创建目录，适用于MicroPython环境
    """
    # 如果目录为空字符串或根目录，直接返回
    if not directory or directory == '/':
        return

    # 处理路径分隔符，确保使用标准格式
    directory = directory.rstrip('/')

    try:
        # 尝试获取目录状态，如果目录存在就直接返回
        print(os.stat(directory))
        print(f'目录已存在: {directory}')
        return
    except OSError:
        # 目录不存在，需要创建
        # 分割路径以获取父目录
        if '/' in directory:
            parent = directory[:directory.rindex('/')]
            if parent and parent != directory:  # 避免无限递归
                ensure_dir(parent)

        try:
            os.mkdir(directory)
            print(f'已创建目录: {directory}')
        except OSError as e:
            # 可能是并发创建导致的冲突，再次检查目录是否存在
            try:
                os.stat(directory)
                print(f'目录已被其他进程创建: {directory}')
            except:
                # 如果仍然不存在，则确实出错了
                print(f'创建目录时出错: {e}')
    except Exception as e:
        print(f'处理目录时出错: {e}')

def analyze_speech(text):
    # 转换为小写，便于匹配
    text = text.lower()

    # 简化正则表达式
    what_pattern = "这是什么|这是甚么|这系什么|这系甚么"
    is_what_query = bool(re.search(what_pattern, text))

    # 检查是否包含"颜色"关键词
    has_color = '颜色' in text

    # 检查是否包含"东西"关键词
    has_thing = '东西' in text

    # 检查是否包含"哪些"关键词
    has_which = '哪些' in text

    # 根据条件判断返回值
    if has_color:
        if has_which:
            return 1  # "颜色" + "哪些"
        else:
            return 2  # 只有"颜色"

    if has_thing:
        if has_which:
            return 3  # "东西" + "哪些"
        else:
            return 4  # 只有"东西"

    if is_what_query:
        if has_color:
            return 2  # "这是什么" + "颜色"
        else:
            return 4

    # 如果没有匹配到任何模式，返回0
    return 0

recog_item = None
latest_frame = None
audio_busy = False
take_snap = False  # 拍照信号
pl = None     # 播报中禁止重复触发
last_name = ""
last_tm = 0
# 自定义自学习类
# Custom self-learning class
class SelfLearningApp(AIBase):
    global recog_item
    """
    自定义自学习应用类，继承自AIBase基类
    Custom self-learning application class extending AIBase.
    """
    def __init__(self, kmodel_path, model_input_size, labels, top_k, threshold, database_path,
                 rgb888p_size=[224,224], display_size=[1920,1080], debug_mode=0, recong_only=False):
        """
        初始化自学习应用
        Initialize the self-learning application.

        参数说明 / Parameters:
          kmodel_path (str): 模型文件路径 / Path to the model file.
          model_input_size (list): 模型输入尺寸 [width, height] / Model input dimensions.
          labels (list): 类别标签列表 / List of label names.
          top_k (int): 选择相似度最高的前K个结果 / Select top K results with highest similarity.
          threshold (float): 特征匹配阈值 / Threshold for feature matching.
          database_path (str): 保存特征文件的目录路径 / Directory path to store feature files.
          rgb888p_size (list): sensor提供图像尺寸，默认[224,224] / Sensor provided image resolution, default [224,224].
          display_size (list): 显示图像的分辨率 / Display image resolution.
          debug_mode (int): 调试模式开关 / Debug mode switch.
          recong_only (bool): 仅识别模式开关 / Recognition-only mode switch.
        """
        # 调用父类的构造函数
        # Call the parent class constructor
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.kmodel_path = kmodel_path  # 模型文件路径 // path of the model file

        # 模型输入分辨率
        # Model input resolution
        self.model_input_size = model_input_size

        self.labels = labels  # 类别标签列表 // list of category labels
        self.database_path = database_path  # 存储特征的数据库路径 // path to store features

        # sensor给到AI的图像分辨率，调整宽度为16的倍数
        # Sensor provides image resolution; align width to multiples of 16
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]

        # 显示图像的分辨率，调整宽度为16的倍数
        # Display resolution; align width to multiples of 16
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]

        self.debug_mode = debug_mode  # 调试模式标志 // debug mode flag

        # 识别阈值，用于特征匹配
        # Recogniton threshold for feature matching
        self.threshold = threshold

        # 选择top_k个相似度大于阈值的结果类别
        # Choose top_k results with similarity above the threshold
        self.top_k = top_k

        # 对应类别注册特征数量，每个类别需要采集的特征文件对数
        # Number of features to be registered per category
        self.features = [3,3,3]

        # 单个特征采集之间间隔的帧数
        # Interval (in frame count) between two feature collections
        self.time_one = 33  # 每特征约3.3秒, 每个物品约10秒

        # 初始化时间累积变量
        # Initialize time accumulation variables
        self.time_all = 0
        self.time_now = 0

        # 类别索引，从0开始，用于依次注册不同类别
        # Category index; used to register features for different categories sequentially
        self.category_index = 0

        # 特征化部分剪切区域的宽高设置
        # Cropping dimensions (width and height) for feature extraction
        self.crop_w = 400
        self.crop_h = 400

        # 根据图像中心计算crop的位置
        # Calculate crop position based on provided image resolution (center crop)
        self.crop_x = self.rgb888p_size[0] / 2.0 - self.crop_w / 2.0
        self.crop_y = self.rgb888p_size[1] / 2.0 - self.crop_h / 2.0

        # 定义画面上输出显示使用的crop位置信息(初始化为0，后续在data_init中计算)
        # Define crop position information for on-screen display (OSD); will be updated later in data_init
        self.crop_x_osd = 0
        self.crop_y_osd = 0
        self.crop_w_osd = 0
        self.crop_h_osd = 0

        # 创建Ai2d实例，用于实现模型输入前的预处理操作
        # Create an Ai2d instance for model preprocessing
        self.ai2d = Ai2d(debug_mode)

        # 设置Ai2d的输入输出格式和数据类型
        # Set Ai2d configuration for input/output formats and data types
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)

        # 是否只识别模式，跳过特征采集等操作
        # Whether to run in recognition-only mode (skip feature collection etc.)
        self.recong_only = recong_only

        # 初始化数据（例如创建存储特征的文件夹、计算OSD窗口位置等）
        # Initialize data (e.g. create directory for storing features and calculate OSD positions)
        self.data_init()

    # 配置预处理操作
    # Configure preprocessing operations
    # 这里使用了crop和resize，Ai2d支持crop/shift/pad/resize/affine
    # Here we perform crop and resize; Ai2d supports crop/shift/pad/resize/affine operations.
    def config_preprocess(self, input_image_size=None):
        """
        配置图像预处理操作
        Configure image preprocessing operations.

        参数:
          input_image_size (list, optional): 输入图像尺寸，可自定义，默认为sensor尺寸 / Optional custom input size; defaults to sensor size
        """
        # 使用ScopedTiming来处理预处理配置的耗时统计（仅在debug_mode开启时）
        # Use ScopedTiming for timing this configuration (only in debug mode)
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            # 根据传入的input_image_size更新输入尺寸，否则使用rgb888p_size
            # Update the ai2d input size based on parameter input_image_size, otherwise use self.rgb888p_size
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            # 配置crop操作，剪切指定区域
            # Set the crop operation to extract a specified region from the input image
            self.ai2d.crop(int(self.crop_x), int(self.crop_y), int(self.crop_w), int(self.crop_h))
            # 配置resize操作，使用tensorflow双线性插值和half_pixel采样模式
            # Set the resize operation using TensorFlow bilinear interpolation with half_pixel mode
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # 构建Ai2d预处理Pipeline，指定输入输出的张量尺寸 [batch, channels, height, width]
            # Build the Ai2d preprocessing pipeline, specifying input and output tensor shapes [N, C, H, W]
            self.ai2d.build(
                [1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                [1, 3, self.model_input_size[1], self.model_input_size[0]]
            )

    # 自定义当前任务的后处理
    # Custom postprocessing for current task
    def postprocess(self, results):
        """
        对模型推理结果进行后处理
        Perform postprocessing on the model results.

        参数:
          results (list): 模型推理返回的结果列表 / List of results returned by the inference.

        返回:
          处理后的结果 / The processed result.
        """
        with ScopedTiming("postprocess", self.debug_mode > 0):
            # 这里只返回results[0][0]，表示只取最主要的结果
            # For simplicity, just return results[0][0] as the primary output.
            return results[0][0]

    # 绘制结果，绘制特征采集框和特征分类框
    # Draw results displaying feature collection and classification boxes
    def draw_result(self, pl, feature):
        global recog_item
        """
        绘制检测结果到屏幕
        Draw the detection results on the screen.

        参数:
          pl (PipeLine): Pipeline示例，用于显示OSD图像 // Pipeline instance for displaying OSD image.
          feature (array): 当前帧提取的特征向量 // Feature vector extracted from current frame.
        """
        # 清空OSD图像
        # Clear the on-screen display (OSD) image
        pl.osd_img.clear()
        with ScopedTiming("display_draw", self.debug_mode > 0):
            # 黄色采集框 ARGB: A=255,R=255,G=255,B=0
            pl.osd_img.draw_rectangle(
                self.crop_x_osd, self.crop_y_osd,
                self.crop_w_osd, self.crop_h_osd,
                color=(255, 255, 255, 0), thickness=4
            )
            if (not self.recong_only and self.category_index < len(self.labels)):
                self.time_now += 1
                idx = int(self.time_now - 1) // self.time_one
                msg = self.labels[self.category_index] + "_" + str(idx) + ".bin"
                if self.time_now % 30 == 0:
                    print(">>> REG: " + msg + "  (frame " + str(self.time_now) + ")")
                try:
                    reg_img = image.Image(640, 480, image.RGB565)
                    reg_img.clear()
                    reg_img.draw_string_advanced(10, 10, 22, msg, color=(255, 255, 0, 0))
                    reg_img.draw_string_advanced(10, 40, 18, "Put object in yellow box", color=(255, 255, 0, 0))
                    Display.show_image(reg_img, 0, 0, Display.LAYER_OSD3)
                except:
                    pass
                # 保存当前特征到指定文件
                # Save the current feature to a file for later matching
                with open(self.database_path + self.labels[self.category_index] + "_" + str(int(self.time_now-1) // self.time_one) + ".bin", 'wb') as f:
                    f.write(feature.tobytes())
                # 若达到该类别预设的特征采集数量，则切换到下一个类别
                # If the number of collected features for this category reaches the preset count, move to the next category
                if (self.time_now // self.time_one == self.features[self.category_index]):
                    self.category_index += 1
                    self.time_all -= self.time_now
                    self.time_now = 0
            else:
                # 如果不是采集特征模式，则进行特征匹配，显示匹配的类别和得分
                # Otherwise, in recognition mode, perform feature matching and show matching category and score.
                results_learn = []
                # 列出数据库中所有feature文件
                # List all feature files in the database directory
                list_features = os.listdir(self.database_path)
                for feature_name in list_features:
                    # 打开feature文件并读取数据
                    # Open the feature file and read its contents
                    with open(self.database_path + feature_name, 'rb') as f:
                        data = f.read()
                    # 将二进制数据转为特征向量
                    # Convert binary data into a feature vector using ulab numpy frombuffer
                    save_vec = np.frombuffer(data, dtype=np.float)
                    # 计算当前特征和保存特征之间的相似度
                    # Calculate similarity between the current feature and the stored feature
                    score = self.getSimilarity(feature, save_vec)
                    # 如果相似度大于预设阈值，则认为匹配上该类别
                    # If the similarity is above the threshold, consider it as a match.
                    if (score > self.threshold):
                        res = feature_name.split("_")
                        is_same = False
                        # 合并同一类别结果，保留相似度更高的结果
                        # Merge the same category results: update if current score is higher.
                        for r in results_learn:
                            if (r["category"] == res[0]):
                                if (r["score"] < score):
                                    r["bin_file"] = feature_name
                                    r["score"] = score
                                is_same = True
                        if (not is_same):
                            # 如果当前结果列表长度小于top_k，直接添加
                            # If current result list is smaller than top_k, add the new match directly.
                            if (len(results_learn) < self.top_k):
                                evec = {}
                                evec["category"] = res[0]
                                evec["score"] = score
                                evec["bin_file"] = feature_name
                                results_learn.append(evec)
                                # 按得分降序排列
                                # Sort the results in descending order by score
                                results_learn = sorted(results_learn, key=lambda x: -x["score"])
                            else:
                                # 如果已达到top_k，但当前得分更高，则进行替换
                                # If top_k results are already present but the new score is higher than the lowest score, replace.
                                if score <= results_learn[self.top_k - 1]["score"]:
                                    continue
                                else:
                                    evec = {}
                                    evec["category"] = res[0]
                                    evec["score"] = score
                                    evec["bin_file"] = feature_name
                                    results_learn.append(evec)
                                    results_learn = sorted(results_learn, key=lambda x: -x["score"])
                                    # 删除最后一个元素以保持长度为top_k
                                    # Remove the element with the lowest score to maintain top_k results.
                                    results_learn.pop()
                # 绘制匹配结果文字信息，依次显示每个匹配类别及其得分
                draw_y = 200
                recog_item = None
                for r in results_learn:
                    txt = r["category"] + " : " + str(r["score"])
                    pl.osd_img.draw_string(50, draw_y, txt, color=(255, 255, 255, 255))
                    draw_y += 30
                    recog_item = r["category"]
                if recog_item:
                    pass



    # 数据初始化：创建文件夹、计算OSD位置以及计算总采集时间
    # Data initialization: create necessary directories, compute OSD positions and total collection time.
    def data_init(self):
        """
        数据初始化，主要包括创建存储特征的目录和计算OSD上显示的剪切区域位置
        Initialize data. Mainly creates the directory for features and calculates the on-screen crop positions.
        """
        # 递归创建数据库目录
        dp = self.database_path.rstrip("/")
        parts = dp.split("/")
        for i in range(2, len(parts) + 1):
            sub = "/".join(parts[:i])
            try:
                os.mkdir(sub)
                print("  created dir: " + sub)
            except:
                pass

        # 注册模式: 自动清理旧特征文件
        if not self.recong_only:
            try:
                old = os.listdir(self.database_path)
                for f in old:
                    if f.endswith(".bin"):
                        os.remove(self.database_path + f)
                        print("  removed old: " + f)
            except:
                pass
        # 计算OSD显示区域位置，将摄像头图像区域按显示分辨率进行缩放转换
        # Calculate the positions for the OSD display region by scaling from sensor resolution to display resolution.
        self.crop_x_osd = int(self.crop_x / self.rgb888p_size[0] * self.display_size[0])
        self.crop_y_osd = int(self.crop_y / self.rgb888p_size[1] * self.display_size[1])
        self.crop_w_osd = int(self.crop_w / self.rgb888p_size[0] * self.display_size[0])
        self.crop_h_osd = int(self.crop_h / self.rgb888p_size[1] * self.display_size[1])
        # 累计所有类别所需采集的帧数，供后续时间控制
        # Sum up all the required frames to be collected from all categories.
        for i in range(len(self.labels)):
            for j in range(self.features[i]):
                self.time_all += self.time_one

    # 计算两个特征向量的余弦相似度
    # Compute the cosine similarity between two feature vectors.
    def getSimilarity(self, output_vec, save_vec):
        """
        计算两个特征向量之间的余弦相似度
        Compute the cosine similarity between two feature vectors.

        参数:
          output_vec: 当前帧提取出的特征向量 / Feature vector from current frame.
          save_vec:  存储的特征向量 / Stored feature vector.

        返回:
          余弦相似度值 / Cosine similarity value.
        """
        # 计算内积
        # Compute inner product.
        tmp = sum(output_vec * save_vec)
        # 计算输出特征向量的模长
        # Compute norm of output vector.
        mold_out = np.sqrt(sum(output_vec * output_vec))
        # 计算保存向量的模长
        # Compute norm of saved vector.
        mold_save = np.sqrt(sum(save_vec * save_vec))
        # 返回归一化的相似度即余弦相似度
        # Return the cosine similarity.
        return tmp / (mold_out * mold_save)

# 自学习例程执行函数
# Self-learning demo execution function
def exce_demo(pl, recong_only=False):
    """
    自学习例程主要流程：
      1. 初始化自学习实例
      2. 启动图像采集、推理、特征采集及后续匹配展示
    Main execution flow for self-learning demo:
      1. Initialize self-learning instance.
      2. Start continuous frame capture, inference, feature collection, and matching display.

    参数:
      pl (PipeLine): Pipeline实例，用于图像采集和显示 // Pipeline instance for frame capture and display.
      recong_only (bool): 是否仅作为识别模式，不进行特征采集 // Whether to run in recognition-only mode.
    """
    global sl, database_path

    # 获取显示和图像参数
    # Retrieve display and image sizes
    display_mode = pl.display_mode
    rgb888p_size = pl.rgb888p_size
    display_size = pl.display_size

    # 模型路径设置
    # Set model path
    kmodel_path = "/sdcard/kmodel/recognition.kmodel"
    # 特征存储路径
    # Database (feature storage) path.
    database_path = "/sdcard/utils/features/"
    # 其它参数设置，例如模型输入尺寸、类别标签、top_k以及匹配阈值
    # Other parameters: model input size, labels, top_k and threshold.
    model_input_size = [224,224]
    # labels = ["耳机", "超声波模块"]
    labels = ["阿莫西林", "诺氟沙星", "感康"]
    top_k = 3
    threshold = 0.65

    try:
        # 初始化自学习实例
        # Initialize the SelfLearningApp instance
        sl = SelfLearningApp(
            kmodel_path,
            model_input_size=model_input_size,
            labels=labels,
            top_k=top_k,
            threshold=threshold,
            database_path=database_path,
            rgb888p_size=rgb888p_size,
            display_size=display_size,
            debug_mode=0,
            recong_only=recong_only
        )
        # 配置预处理操作
        # Configure the preprocessing operations
        sl.config_preprocess()
        # 无限循环处理每一帧数据
        # Infinite loop to process each frame
        while True:
            global latest_frame, take_snap
            img = pl.get_frame()
            latest_frame = img
            time.sleep_ms(1)

            if take_snap:
                take_snap = False
                try:
                    # 从OSD复制画面(含摄像头+叠加层)
                    w = pl.osd_img.width()
                    h = pl.osd_img.height()
                    simg = image.Image(w, h, image.RGB565)
                    simg.draw_image(pl.osd_img, 0, 0)
                    simg.save("/sdcard/snapshot.jpg")
                    print("  snap OK: " + str(os.stat("/sdcard/snapshot.jpg")[6]))
                except Exception as e:
                    print("  snap err: " + str(e))

            res = sl.run(img)
            time.sleep_ms(1)
            sl.draw_result(pl, res)
            time.sleep_ms(1)
            pl.show_image()
            time.sleep_ms(1)
            gc.collect()
            time.sleep_ms(5)
    except Exception as e:
        # 捕获异常后打印提示信息
        # Print message when an exception is caught.
        print("自学习例程退出", e)
    finally:
        # 最终退出时执行反初始化
        # Finally, deinitialize the demo.
        exit_demo()

# 退出例程，反初始化资源并清除特征保存文件夹
# Exit routine: cleanup resources and remove stored feature files
def exit_demo():
    global sl, database_path
#    # 删除features文件夹下所有文件，并删除文件夹本身
#    # Remove all files within the features directory and the directory itself
#    stat_info = os.stat(database_path)
#    # 判断目录是否为文件夹（目录标志位0x4000）
#    # Check if database_path is a directory based on stat info (0x4000 indicates a directory)
#    if (stat_info[0] & 0x4000):
#        list_files = os.listdir(database_path)
#        for l in list_files:
#            os.remove(database_path + l)
#    os.rmdir(database_path)
    # 执行自学习实例的反初始化，释放资源
    # Deinitialize the self-learning instance and free up resources.
    sl.deinit()

recorder = AudioRecorder()
voice_text_ret = None

# ============================================================
# DashScope API 函数 (替换笔记本:3001服务器)
# ============================================================

MODEL_OMNI = "qwen-omni-turbo"

def upload_to_oss(filename, model=MODEL_OMNI):
    """上传文件到DashScope OSS (音频或图片)"""
    print("  Uploading to OSS...")
    gc.collect()
    policy_url = ("https://dashscope.aliyuncs.com/api/v1/uploads"
                  "?action=getPolicy&model=" + model)
    headers = {"Authorization": "Bearer " + API_KEY}
    resp = requests2.get(policy_url, headers=headers, timeout=30)
    if resp.status_code != 200:
        print("  getPolicy failed: " + str(resp.status_code))
        return None
    policy = resp.json["data"]
    gc.collect()
    file_name = filename.split("/")[-1]
    key = policy["upload_dir"] + "/" + file_name
    with open(filename, "rb") as f:
        file_data = f.read()
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    fields = {
        "OSSAccessKeyId": policy["oss_access_key_id"],
        "Signature": policy["signature"],
        "policy": policy["policy"],
        "x-oss-object-acl": policy["x_oss_object_acl"],
        "x-oss-forbid-overwrite": policy["x_oss_forbid_overwrite"],
        "key": key, "success_action_status": "200"
    }
    parts = []
    for name, value in fields.items():
        parts.append("--" + boundary + "\r\nContent-Disposition: form-data; name=\"" + name + "\"\r\n\r\n" + value + "\r\n")
    parts.append("--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"" + file_name + "\"\r\nContent-Type: application/octet-stream\r\n\r\n")
    text_bytes = "".join(parts).encode("utf-8")
    end_bytes = ("\r\n--" + boundary + "--\r\n").encode("utf-8")
    body = text_bytes + file_data + end_bytes
    resp = requests2.post(policy["upload_host"], data=body,
                          headers={"Content-Type": "multipart/form-data; boundary=" + boundary}, timeout=90)
    if resp.status_code == 200:
        oss_url = "oss://" + key
        print("  OSS: " + oss_url)
        return oss_url
    print("  OSS post failed: " + str(resp.status_code))
    return None


def ask_qwen_omni(audio_oss, image_oss):
    """Qwen-Omni: 同时理解语音+画面, 直接回答"""
    print("  Asking Qwen-Omni...")
    gc.collect()
    ctx = "你是药品管理助手。请用中文简短口语化回答。"
    if recog_item and recog_item in MEDICINE_INFO:
        ctx += "摄像头本地识别到: " + recog_item + "。" + MEDICINE_INFO[recog_item]
    content_list = []
    if image_oss:
        content_list.append({"image": image_oss})
    content_list.append({"audio": audio_oss})
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    headers = {"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json",
               "X-DashScope-OssResourceResolve": "enable"}
    body = {"model": MODEL_OMNI, "input": {"messages": [
        {"role": "system", "content": [{"text": ctx}]},
        {"role": "user", "content": content_list}
    ]}}
    resp = requests2.post(url, headers=headers, json_data=body, timeout=90)
    print("  Omni status: " + str(resp.status_code))
    if resp.status_code != 200:
        try:
            err = resp.text
            if isinstance(err, bytes):
                err = err.decode('utf-8')
            print("  Omni error body: " + str(err[:300]))
        except:
            pass
        return None
    try:
        raw = resp.text if isinstance(resp.text, str) else resp.text.decode('utf-8')
        result = ujson.loads(raw)
        reply = result["output"]["choices"][0]["message"]["content"][0]["text"]
        print("  Reply: " + reply)
        return reply
    except Exception as e:
        print("  Parse err: " + str(e))
    return None


def text_to_speech_dashscope(text):
    """Qwen3-TTS文字转语音"""
    text = text[:60]
    print("  TTS: " + text[:40] + "...")
    gc.collect()
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    headers = {"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"}
    body = {"model": "qwen3-tts-flash", "input": {"text": text, "voice": "Cherry", "language_type": "Chinese"}}
    resp = requests2.post(url, headers=headers, json_data=body, timeout=90)
    if resp.status_code != 200:
        print("  TTS API err: " + str(resp.status_code))
        return False
    try:
        raw = resp.text if isinstance(resp.text, str) else resp.text.decode('utf-8')
        audio_url = ujson.loads(raw)["output"]["audio"]["url"]
    except:
        return False
    # 下载带重试
    for retry in range(3):
        gc.collect()
        audio_resp = requests2.get(audio_url, timeout=90)
        if audio_resp.status_code == 200:
            data = audio_resp.content
            if len(data) > 1000:
                with open("/sdcard/tts_reply.wav", "wb") as f:
                    f.write(data)
                print("  TTS saved: " + str(len(data)) + " bytes")
                return True
        print("  download retry " + str(retry + 1))
        time.sleep(1)
    return False


def play_audio_file(filename):
    """播放WAV文件"""
    try:
        with open(filename, 'rb') as f: pass
    except OSError:
        return
    spk2 = YbSpeaker()
    spk2.enable()
    wf = wave.open(filename, 'rb')
    CH = int(wf.get_framerate() / 25)
    p = PyAudio(); p.initialize(CH)
    stream = p.open(format=p.get_format_from_width(wf.get_sampwidth()),
                    channels=wf.get_channels(), rate=wf.get_framerate(),
                    output=True, frames_per_buffer=CH)
    stream.volume(vol=100)
    bw = 0
    d = wf.read_frames(CH)
    while d:
        stream.write(d); bw += len(d); d = wf.read_frames(CH)
    dur = bw / (wf.get_framerate() * wf.get_sampwidth() * wf.get_channels())
    time.sleep(dur + 1.0)
    try: stream.stop_stream(); stream.close(); p.terminate(); wf.close(); spk2.disable()
    except: pass


def capture_snapshot():
    """多种方式尝试保存摄像头画面"""
    global pl, latest_frame
    path = "/sdcard/snapshot.jpg"
    # 方法1: get_frame直接保存
    try:
        frame = pl.get_frame()
        if hasattr(frame, 'save'):
            frame.save(path)
            if os.stat(path)[6] > 1000:
                print("  snap OK: " + str(os.stat(path)[6]))
                return path
    except Exception as e:
        print("  m1: " + str(e))
    # 方法2: 从latest_frame转换
    try:
        if latest_frame is not None:
            w, h = 640, 480
            simg = image.Image(w, h, image.RGB565)
            if hasattr(latest_frame, 'copy_to'):
                latest_frame.copy_to(simg)
            else:
                simg.draw_image(latest_frame, 0, 0)
            simg.save(path)
            if os.stat(path)[6] > 1000:
                print("  snap OK: " + str(os.stat(path)[6]))
                return path
    except Exception as e:
        print("  m2: " + str(e))
    # 方法3: OSD图像兜底
    try:
        w = pl.osd_img.width()
        h = pl.osd_img.height()
        img2 = image.Image(w, h, image.RGB565)
        img2.draw_image(pl.osd_img, 0, 0)
        img2.save(path)
        if os.stat(path)[6] > 1000:
            print("  snap OK(osd): " + str(os.stat(path)[6]))
            return path
    except Exception as e:
        print("  m3: " + str(e))
    return None


def local_respond(name):
    """本地播报: 播放预录WAV (不依赖网络/KPU)"""
    wav_path = "/sdcard/med_wav/" + name + ".wav"
    print("  Local play: " + wav_path)
    try:
        with open(wav_path, 'rb') as f:
            pass
        play_audio_file(wav_path)
        return
    except OSError:
        print("  WAV not found, falling back to cloud TTS")
    # 兜底: 云端TTS
    info = MEDICINE_INFO.get(name, "")
    if info:
        if text_to_speech_dashscope(info):
            play_audio_file("/sdcard/tts_reply.wav")
            try:
                os.remove("/sdcard/tts_reply.wav")
            except:
                pass


def audio_to_text(audio_oss):
    """Qwen-Audio-Turbo 语音转文字"""
    print("  ASR...")
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    headers = {"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json",
               "X-DashScope-OssResourceResolve": "enable"}
    body = {"model": "qwen-audio-turbo-latest", "input": {"messages": [
        {"role": "system", "content": [{"text": "你是一个语音转文字工具，把用户的语音转成文字输出。"}]},
        {"role": "user", "content": [{"audio": audio_oss}]}
    ]}}
    resp = requests2.post(url, headers=headers, json_data=body, timeout=90)
    if resp.status_code == 200:
        try:
            raw = resp.text if isinstance(resp.text, str) else resp.text.decode('utf-8')
            text = ujson.loads(raw)["output"]["choices"][0]["message"]["content"][0]["text"]
            print("  ASR: " + text)
            return text
        except Exception as e:
            print("  ASR parse err: " + str(e))
    return None


def ask_qwen_omni_text_img(image_oss, question_text):
    """Qwen-Omni看图回答, 无图时用Qwen-Turbo文字问答"""
    gc.collect()
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    headers = {"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json",
               "X-DashScope-OssResourceResolve": "enable"}
    if image_oss:
        print("  Omni (img+text)...")
        body = {"model": MODEL_OMNI, "input": {"messages": [{
            "role": "system", "content": [{"text": "用一两句话简短回答，不超过15字。"}]
        }, {
            "role": "user", "content": [
                {"image": image_oss},
                {"text": question_text}
            ]
        }]}}
    else:
        print("  (no image, using text fallback)")
        return ask_qwen_text_fallback(question_text)
    resp = requests2.post(url, headers=headers, json_data=body, timeout=90)
    print("  status: " + str(resp.status_code))
    if resp.status_code != 200:
        try:
            err = resp.text if isinstance(resp.text, str) else resp.text.decode('utf-8')
            print("  err: " + str(err[:300]))
        except:
            pass
        # 兜底: 用Qwen-Turbo纯文字
        return ask_qwen_text_fallback(question_text)
    try:
        raw = resp.text if isinstance(resp.text, str) else resp.text.decode('utf-8')
        reply = ujson.loads(raw)["output"]["choices"][0]["message"]["content"][0]["text"]
        print("  Reply: " + reply)
        return reply
    except Exception as e:
        print("  Parse err: " + str(e))
    return ask_qwen_text_fallback(question_text)


def ask_qwen_text_fallback(question_text):
    """Qwen-Turbo纯文字兜底"""
    print("  Qwen-Turbo fallback...")
    gc.collect()
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"}
    body = {"model": "qwen-turbo", "messages": [
        {"role": "system", "content": "用一两句话简短回答。"},
        {"role": "user", "content": question_text}
    ]}
    resp = requests2.post(url, headers=headers, json_data=body, timeout=90)
    if resp.status_code == 200:
        try:
            raw = resp.text if isinstance(resp.text, str) else resp.text.decode('utf-8')
            return ujson.loads(raw)["choices"][0]["message"]["content"]
        except:
            pass
    return None


def async_get_voice_to_text():
    """录音→ASR + 照片(主线程已拍)→Qwen-Omni"""
    global voice_text_ret
    voice_text_ret = None
    try:
        print("  [1] upload audio...")
        audio_oss = upload_to_oss("/sdcard/rec.wav", "qwen-audio-turbo")
        if not audio_oss:
            voice_text_ret = ""
            return
        print("  [2] ASR...")
        text = audio_to_text(audio_oss)
        if not text:
            voice_text_ret = ""
            return
        print("  [3] upload snapshot...")
        img_oss = None
        try:
            if os.stat("/sdcard/snapshot.jpg")[6] > 1000:
                img_oss = upload_to_oss("/sdcard/snapshot.jpg", MODEL_OMNI)
        except:
            pass
        print("  [4] Qwen-Omni(img=" + str(img_oss is not None) + ")...")
        reply = ask_qwen_omni_text_img(img_oss, text)
        voice_text_ret = reply if reply else ""
    except Exception as e:
        print("  err: " + str(e))
        voice_text_ret = ""

record_flag = False
key = YbKey()

def async_record():
    global recorder,record_flag
    record_flag = False
    recorder.record_with_button("/sdcard/rec.wav", key)
    record_flag = True


def voice_serv():
    global audio_busy, last_name, last_tm, voice_text_ret, record_flag

    _thread.start_new_thread(connect_wifi, ())
    key = YbKey()

    print("Voice service ready. Auto-recog or press button for cloud.")

    while True:
        rgb.show_rgb((0, 255, 0))

        # 自动路径: 本地识别到药品 → 播WAV
        if recog_item and recog_item in MEDICINE_INFO and not audio_busy:
            if recog_item != last_name:
                name = recog_item
                print("  Auto: " + name)
                audio_busy = True
                last_name = name
                rgb.show_rgb((0, 0, 255))
                try:
                    img2 = image.Image(640, 480, image.RGB565)
                    img2.clear()
                    img2.draw_string_advanced(10, 10, 16, name, color=(255, 255, 0, 0))
                    Display.show_image(img2, 0, 0, Display.LAYER_OSD3)
                except:
                    pass
                local_respond(name)
                try:
                    img2.clear()
                    Display.show_image(img2, 0, 0, Display.LAYER_OSD3)
                except:
                    pass
                audio_busy = False

        if not recog_item:
            last_name = ""

        # 按键路径: 按住说话 → 云端Qwen-Omni → TTS回答
        if key.is_pressed() and not audio_busy:
            audio_busy = True
            rgb.show_rgb((255, 0, 0))
            print("  Cloud: recording...")
            record_flag = False
            _thread.start_new_thread(async_record, ())
            while record_flag == False:
                time.sleep_ms(5)
            # 触发主线程拍照
            global take_snap
            take_snap = True
            time.sleep_ms(500)  # 等主线程拍照完成
            rgb.show_rgb((0, 0, 255))
            async_get_voice_to_text()
            while voice_text_ret is None:
                time.sleep_ms(5)
            if voice_text_ret and voice_text_ret.strip():
                tts_text = voice_text_ret[:60]
                print("  Cloud reply: " + tts_text)
                if text_to_speech_dashscope(tts_text):
                    play_audio_file("/sdcard/tts_reply.wav")
                else:
                    play_audio_file("/sdcard/utils/saywhat.wav")
            else:
                play_audio_file("/sdcard/utils/sayagain.wav")
            audio_busy = False

        time.sleep_ms(50)



# 主程序入口
if __name__ == "__main__":
    # 启动指示: 蓝闪2次
    for _ in range(2):
        rgb.show_rgb((0, 0, 255))
        time.sleep_ms(100)
        rgb.show_rgb((0, 0, 0))
        time.sleep_ms(100)

    rgb888p_size = [1280, 960]
    display_size = [640, 480]
    display_mode = "lcd"

    # 一次性WAV生成: 联网下载TTS音频, 之后纯本地播放
    if GEN_WAV:
        print("=== 生成播报WAV ===")
        while not connect_wifi():
            time.sleep(3)
        try:
            os.mkdir("/sdcard/med_wav")
        except:
            pass
        for name in MEDICINE_INFO:
            fpath = "/sdcard/med_wav/" + name + ".wav"
            try:
                with open(fpath, 'rb') as f:
                    print("  skip " + name + " (exists)")
                    continue
            except:
                pass
            print("  generating " + name + " ...")
            if text_to_speech_dashscope(MEDICINE_INFO[name]):
                try:
                    with open("/sdcard/tts_reply.wav", "rb") as src:
                        with open(fpath, "wb") as dst:
                            dst.write(src.read())
                    print("  saved " + fpath)
                except Exception as e:
                    print("  copy err: " + str(e))
        print("=== WAV生成完毕, 请将 GEN_WAV 改为 False ===")

    if REGISTER_MODE:
        print("=== 注册模式: 请依次将药盒放入黄框 ===")
    else:
        print("=== 识别模式 ===")

    _thread.start_new_thread(voice_serv, ())
    pl = PipeLine(rgb888p_size=rgb888p_size, display_size=display_size, display_mode=display_mode)
    pl.create()
    exce_demo(pl, not REGISTER_MODE)

