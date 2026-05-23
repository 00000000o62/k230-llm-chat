from media.display import *
from media.media import *
from media.pyaudio import *
import media.wave as wave
import time, os, sys, gc
import lvgl as lv
from machine import TOUCH
import json
import _thread
import YbRequests as urequests
from ybUtils.YbKey import YbKey
from ybUtils.YbSpeaker import YbSpeaker
from ybUtils.YbBuzzer import YbBuzzer
from ybUtils.YbRGB import YbRGB
import re

def network_use_wlan(ssid,key):
    import network
    sta = network.WLAN(0)
    sta.connect(ssid,key)
    while not sta.isconnected():
        time.sleep(1)
    return sta.ifconfig()[0]


def display_init():
    pass
    Display.init(Display.ST7701, width = 640, height = 480, to_ide = True)
    MediaManager.init()
    pass

def display_deinit():
    pass
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(50)
    Display.deinit()
    MediaManager.deinit()
    pass

def disp_drv_flush_cb(disp_drv, area, color):
    global disp_img1, disp_img2
    try:
        if disp_drv.flush_is_last() == True:
            if disp_img1.virtaddr() == uctypes.addressof(color.__dereference__()):
                Display.show_image(disp_img1)
            else:
                Display.show_image(disp_img2)
            time.sleep(0.01)
        disp_drv.flush_ready()
    except Exception as e:
        pass
        pass

class touch_screen():
    def __init__(self):
        pass
        self.state = lv.INDEV_STATE.RELEASED
        self.indev_drv = lv.indev_create()
        self.indev_drv.set_type(lv.INDEV_TYPE.POINTER)
        self.indev_drv.set_read_cb(self.callback)
        self.touch = TOUCH(0)
        pass

    def callback(self, driver, data):
        try:
            x, y, state = 0, 0, lv.INDEV_STATE.RELEASED
            tp = self.touch.read(1)
            if len(tp):
                x, y, event = tp[0].x, tp[0].y, tp[0].event
                if event == 2 or event == 3:
                    state = lv.INDEV_STATE.PRESSED
            data.point = lv.point_t({'x': x, 'y': y})
            data.state = state
        except Exception as e:
            pass
            pass

def lvgl_init():
    global disp_img1, disp_img2
    pass
    lv.init()
    disp_drv = lv.disp_create(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    disp_drv.set_flush_cb(disp_drv_flush_cb)
    disp_img1 = image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.BGRA8888)
    disp_img2 = image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.BGRA8888)
    disp_drv.set_draw_buffers(disp_img1.bytearray(), disp_img2.bytearray(), disp_img1.size(), lv.DISP_RENDER_MODE.FULL)
    tp = touch_screen()
    pass

def lvgl_deinit():
    global disp_img1, disp_img2
    pass
    lv.deinit()
    del disp_img1
    del disp_img2
    pass

# 定义颜色
COLOR_PRIMARY = lv.color_hex(0x131a23)
COLOR_BG = lv.color_hex(0xF5F5F5)
# COLOR_CHAT_BG = lv.color_hex(0xFFFFFF)
COLOR_CHAT_BG = lv.color_hex(0x404142)
COLOR_SELF_MSG = lv.color_hex(0xDCF8C6)
COLOR_OTHER_MSG = lv.color_hex(0xECEFF1)
COLOR_TEXT = lv.color_hex(0x333333)
COLOR_INPUT_BG = lv.color_hex(0xFFFFFF)

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
            # 按住录制，松开停止
            while key.is_pressed() and self.is_recording:
                if self.exit_check():
                    break
                data = self.input_stream.read()
                self.frames.append(data)

            print("停止录制...")
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



# 修改后的键盘管理类
class KeyboardManager:
    def __init__(self, screen, textarea, voice_recorder=None):
        self.screen = screen
        self.target_textarea = textarea
        self.recorder = voice_recorder
        self.keyboard_visible = False
        self.v2t_status = 0
        self.v2t_res = None
        self.create_keyboard()

    def create_keyboard(self):
        # 创建键盘容器，覆盖整个屏幕，使用固定分辨率
        self.keyboard_container = lv.obj(self.screen)
        self.keyboard_container.set_size(DISPLAY_WIDTH, DISPLAY_HEIGHT)  # 使用固定分辨率
        self.keyboard_container.align(lv.ALIGN.TOP_LEFT, 0, 0)
        self.keyboard_container.set_style_bg_opa(lv.OPA.TRANSP, 0)
        self.keyboard_container.set_style_pad_all(0, 0)  # 移除所有填充
        self.keyboard_container.set_style_border_width(0, 0)  # 移除边框
        self.keyboard_container.add_flag(lv.obj.FLAG.HIDDEN)

        # 创建半透明遮罩层
        self.overlay = lv.obj(self.keyboard_container)
        self.overlay.set_size(DISPLAY_WIDTH, DISPLAY_HEIGHT)  # 同样使用固定分辨率
        self.overlay.set_style_bg_color(lv.color_hex(0x000000), 0)
        self.overlay.set_style_bg_opa(lv.OPA._50, 0)  # 半透明
        self.overlay.set_style_pad_all(0, 0)  # 移除填充
        self.overlay.set_style_border_width(0, 0)  # 移除边框
        self.overlay.add_event(self.overlay_click_cb, lv.EVENT.CLICKED, None)

        # 创建键盘
        self.keyboard = lv.keyboard(self.keyboard_container)
        self.keyboard.set_size(DISPLAY_WIDTH, int(DISPLAY_HEIGHT * 0.4))  # 保持原有比例
        self.keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.keyboard.set_style_bg_color(lv.color_hex(0xF5F5F7), 0)
        self.keyboard.set_style_radius(0, 0)
        self.keyboard.set_style_shadow_width(5, 0)
        self.keyboard.set_style_shadow_opa(lv.OPA._20, 0)
        self.keyboard.set_style_pad_all(0, 0)  # 移除填充

        # 创建临时输入显示区域
        self.temp_input_display = lv.textarea(self.keyboard_container)
        self.keyboard.set_textarea(self.temp_input_display)
        self.temp_input_display.set_size(DISPLAY_WIDTH, 60)
        self.temp_input_display.align_to(self.keyboard, lv.ALIGN.OUT_TOP_MID, 0, 0)
        self.temp_input_display.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
        self.temp_input_display.set_style_border_width(1, 0)
        self.temp_input_display.set_style_border_color(lv.color_hex(0xDDDDDD), 0)
        self.temp_input_display.set_style_pad_all(10, 0)
        self.temp_input_display.set_one_line(False)
        self.temp_input_display.set_style_text_align(lv.TEXT_ALIGN.LEFT, 0)
        self.temp_input_display.set_text("")

        # 创建语音输入界面
        self.voice_input_keyboard = lv.obj(self.keyboard)
        self.voice_input_keyboard.set_size(DISPLAY_WIDTH, int(DISPLAY_HEIGHT * 0.4))
        self.voice_input_keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.voice_input_keyboard.set_style_bg_color(lv.color_hex(0xF5F5F7), 0)
        self.voice_input_keyboard.set_style_pad_all(15, 0)
        self.voice_input_keyboard.add_flag(lv.obj.FLAG.HIDDEN)

        # 顶部返回按钮区域
        top_container = lv.obj(self.voice_input_keyboard)
        top_container.set_size(DISPLAY_WIDTH, 50)
        top_container.align(lv.ALIGN.TOP_MID, 0, 0)
        top_container.set_style_bg_opa(0, 0)
        top_container.set_style_border_width(0, 0)
        top_container.set_style_pad_all(0, 0)

        vi_ret_btn = lv.btn(top_container)
        vi_ret_btn.set_size(40, 40)
        vi_ret_btn.align(lv.ALIGN.LEFT_MID, 5, 0)
        vi_ret_btn.set_style_radius(20, 0)
        vi_ret_btn.set_style_bg_color(lv.color_hex(0xE9E9EB), 0)
        vi_ret_btn.add_event(self.vi_ret_btn_click, lv.EVENT.CLICKED, None)

        ret_label = lv.label(vi_ret_btn)
        ret_label.set_text(lv.SYMBOL.LEFT)
        ret_label.center()

        self.vi_hint_label = lv.label(top_container)
        self.vi_hint_label.set_text("轻触麦克风图标开始录音")
        self.vi_hint_label.align(lv.ALIGN.CENTER, 0, 0)
        self.vi_hint_label.set_style_text_color(lv.color_hex(0x666666), 0)

        # 中央区域 - 用于显示状态和波形
        center_container = lv.obj(self.voice_input_keyboard)
        center_container.set_size(DISPLAY_WIDTH, 80)
        center_container.align_to(top_container, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)
        center_container.set_style_bg_opa(0, 0)
        center_container.set_style_border_width(0, 0)
        center_container.set_style_pad_all(0, 0)

        self.vi_wave_area = lv.obj(center_container)
        self.vi_wave_area.set_size(300, 80)
        self.vi_wave_area.align(lv.ALIGN.CENTER, 0, 0)
        self.vi_wave_area.set_style_bg_opa(0, 0)
        self.vi_wave_area.set_style_border_width(0, 0)
        self.vi_wave_area.set_style_pad_all(0, 0)
        self.vi_wave_area.add_flag(lv.obj.FLAG.HIDDEN)

        for i in range(5):
            wave_circle = lv.obj(self.vi_wave_area)
            wave_circle.set_size(20, 20)
            wave_circle.align(lv.ALIGN.CENTER, 0, 0)
            wave_circle.set_style_radius(lv.RADIUS_CIRCLE, 0)
            wave_circle.set_style_border_width(2, 0)
            wave_circle.set_style_bg_opa(0, 0)
            wave_circle.set_style_border_color(lv.color_hex(0x007AFF), 0)
            wave_circle.set_style_border_opa(lv.OPA._50, 0)
            setattr(self, f'wave_circle_{i}', wave_circle)

        # 底部区域 - 放置录音按钮
        bottom_container = lv.obj(self.voice_input_keyboard)
        bottom_container.set_size(DISPLAY_WIDTH, 90)
        bottom_container.align(lv.ALIGN.BOTTOM_MID, 0, -10)
        bottom_container.set_style_bg_opa(0, 0)
        bottom_container.set_style_border_width(0, 0)
        bottom_container.set_style_pad_all(0, 0)

        self.vi_btn = lv.btn(bottom_container)
        self.vi_btn.set_size(80, 80)
        self.vi_btn.align(lv.ALIGN.CENTER, 0, 5)
        self.vi_btn.set_style_radius(40, 0)
        self.vi_btn.set_style_bg_color(lv.color_hex(0x007AFF), 0)
        self.vi_btn.set_style_shadow_width(10, 0)
        self.vi_btn.set_style_shadow_opa(lv.OPA._30, 0)
        self.vi_btn.add_event(self.vi_btn_click, lv.EVENT.CLICKED, None)

        self.vi_label = lv.label(self.vi_btn)
        self.vi_label.set_text(lv.SYMBOL.PLAY)
        self.vi_label.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
        self.vi_label.set_style_text_font(lv.font_yb_cn_16, 0)
        self.vi_label.center()

        self.keyboard.add_event(self.custom_keyboard_event_cb, lv.EVENT.VALUE_CHANGED, None)
        self.keyboard.set_mode(lv.keyboard.MODE.TEXT_LOWER)

    def overlay_click_cb(self, evt):
        self.hide()

    def show(self):
        self.keyboard_container.clear_flag(lv.obj.FLAG.HIDDEN)
        self.keyboard_visible = True
        current_text = self.target_textarea.get_text()
        self.temp_input_display.set_text(current_text)
        self.temp_input_display.set_cursor_pos(len(current_text))
        self.temp_input_display.add_state(lv.STATE.FOCUSED)

    def hide(self):
        self.keyboard_container.add_flag(lv.obj.FLAG.HIDDEN)
        self.keyboard_visible = False
        self.target_textarea.set_text(self.temp_input_display.get_text())
        lv.group_focus_obj(None)

    def custom_keyboard_event_cb(self, e):
        kb = lv.keyboard.__cast__(e.get_target())
        code = e.get_code()
        btn_id = kb.get_selected_btn()
        if code == lv.EVENT.VALUE_CHANGED and btn_id == 36:
            kb.set_mode(lv.keyboard.MODE.TEXT_LOWER)
            self.voice_input_keyboard.clear_flag(lv.obj.FLAG.HIDDEN)

    def vi_ret_btn_click(self, e):
        if hasattr(self, 'record_timer'):
            self.record_timer._del()
            delattr(self, 'record_timer')
        self.voice_input_keyboard.add_flag(lv.obj.FLAG.HIDDEN)

    def vi_btn_click(self, event):
        btn = lv.btn.__cast__(event.get_target())
        if btn.has_state(lv.STATE.DISABLED):
            return
        self.vi_label.set_text(lv.SYMBOL.STOP)
        self.vi_wave_area.clear_flag(lv.obj.FLAG.HIDDEN)
        self.vi_hint_label.set_text("请讲话...")
        btn.add_state(lv.STATE.DISABLED)
        btn.set_style_bg_color(lv.color_hex(0xFF3B30), 0)
        self.animate_voice_waves()
        self.countdown_label = lv.label(self.voice_input_keyboard)
        self.countdown_seconds = 5
        self.countdown_label.set_text(f"{self.countdown_seconds}s")
        self.countdown_label.align(lv.ALIGN.TOP_MID, 0, 50)
        self.countdown_label.set_style_text_color(lv.color_hex(0x007AFF), 0)
        self.countdown_label.set_style_text_font(lv.font_yb_cn_16, 0)

        def recording_done(timer):
            try:
                if hasattr(self, 'countdown_label') and self.countdown_label:
                    self.countdown_label.delete()
                if hasattr(self, 'wave_anims'):
                    for anim in self.wave_anims:
                        lv.anim_del(anim, None)
                    self.wave_anims = []
                time.sleep_us(1)
                timer._del()
                if hasattr(self, 'record_timer'):
                    delattr(self, 'record_timer')
                if hasattr(self, 'countdown_timer'):
                    delattr(self, 'countdown_timer')
            except Exception as e:
                pass

        def countdown_timer_cb(timer):
            try:
                self.countdown_seconds -= 1
                if self.countdown_seconds > 0:
                    self.countdown_label.set_text(str(self.countdown_seconds))
                else:
                    timer._del()
                    lv.timer_create(recording_done, 1, None)
            except Exception as e:
                pass

        self.countdown_timer = lv.timer_create(countdown_timer_cb, 1000, None)
        _thread.start_new_thread(self.voice_to_text, ())

    def animate_voice_waves(self):
        for i in range(5):
            circle = getattr(self, f'wave_circle_{i}')
            anim = lv.anim_t()
            anim.init()
            anim.set_var(circle)
            anim.set_values(20, 120 + i * 20)
            anim.set_time(1000 + i * 300)
            anim.set_repeat_count(lv.ANIM_REPEAT_INFINITE)
            anim.set_path_cb(lv.anim_t.path_ease_out)
            def cb(circle, val):
                circle.set_size(val, val)
                circle.align(lv.ALIGN.CENTER, 0, 0)
                opacity = max(10, int(120 - val/2))
                circle.set_style_border_opa(opacity, 0)
            anim.set_custom_exec_cb(lambda a, val: cb(circle, val))
            anim.start()
            if not hasattr(self, 'wave_anims'):
                self.wave_anims = []
            self.wave_anims.append(anim)

    def voice_to_text(self):
        if not self.recorder:
            return
        wav_path = "/data/tmp_v.wav"
        if self.recorder.record_to_file(6, wav_path):
            self.vi_hint_label.set_text("识别中 ...")
            self.vi_btn.add_state(lv.STATE.DISABLED)
            base64_result = self.recorder.file_to_base64(wav_path)
            if base64_result:
                self.v2t_status = 1
                res = json.loads(req(base64_result[1], base64_result[0]))
                self.v2t_status = 0
                self.v2t_res = res
                if res["err_no"] == 0:
                    strs = "".join(res["result"])
                    self.temp_input_display.add_text(strs)
                    self.vi_label.set_text(lv.SYMBOL.PLAY)
                    self.vi_wave_area.add_flag(lv.obj.FLAG.HIDDEN)
                    self.vi_hint_label.set_text("轻触麦克风图标开始录音")
                    self.vi_btn.clear_state(lv.STATE.DISABLED)
                    self.vi_btn.set_style_bg_color(lv.color_hex(0x007AFF), 0)
                    self.v2t_res = None
                    self.hide()
                else:
                    self.vi_label.set_text(lv.SYMBOL.PLAY)
                    self.vi_wave_area.add_flag(lv.obj.FLAG.HIDDEN)
                    self.vi_hint_label.set_text("识别失败，请重试")
                    self.vi_btn.clear_state(lv.STATE.DISABLED)
                    self.vi_btn.set_style_bg_color(lv.color_hex(0x007AFF), 0)
                    self.v2t_res = None

# 修改后的ChatUI类
class ChatUI:
    def __init__(self, recorder=None):
        pass
        self.scr = lv.scr_act()
        self.scr.set_scroll_dir(lv.DIR.NONE)
        lv.scr_load(self.scr)
        self.recorder = recorder
        self.create_header()
        self.create_chat_area()
        self.create_input_area()
        self.keyboard_mgr = KeyboardManager(self.scr, self.ta, recorder)
        self.chat_history = []
        self.v2t_status = 0
        self.v2t_res = None
        pass

    def create_header(self):
        pass
        self.header = lv.obj(self.scr)
        self.header.set_size(lv.pct(100), 50)
        self.header.align(lv.ALIGN.TOP_MID, 0, 0)
        self.header.set_style_bg_color(COLOR_PRIMARY, 0)
        self.header.set_style_pad_all(0, 0)
        self.header.set_style_radius(0, 0)
        self.header.set_style_border_width(0, 0)
        self.title = lv.label(self.header)
        self.title.set_text("LLM 大模型")
        self.title.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
        self.title.center()
        pass

    def create_chat_area(self):
        pass
        self.chat_container = lv.obj(self.scr)
        self.chat_container.set_size(lv.pct(100), DISPLAY_HEIGHT - 110)  # 固定高度
        self.chat_container.align_to(self.header, lv.ALIGN.OUT_BOTTOM_MID, 0, 0)
        self.chat_container.set_style_bg_color(COLOR_CHAT_BG, 0)
        self.chat_container.set_style_border_width(0, 0)
        self.chat_container.set_style_radius(0, 0)
        self.chat_list = lv.obj(self.chat_container)
        self.chat_list.set_size(640, DISPLAY_HEIGHT - 110)
        self.chat_list.align(lv.ALIGN.TOP_MID, 0, 0)
        self.chat_list.set_style_pad_all(5, 0)
        self.chat_list.set_style_border_width(0, 0)
        self.chat_list.set_style_bg_color(COLOR_CHAT_BG, 0)
        self.chat_list.add_flag(lv.obj.FLAG.SCROLLABLE)
        self.chat_list.set_scroll_dir(lv.DIR.VER)
        self.chat_list.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.chat_list.set_style_pad_column(10, 0)
        self.chat_list.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.chat_container.clear_flag(lv.obj.FLAG.SCROLLABLE)
        pass

    def create_input_area(self):
        pass
        self.input_area = lv.obj(self.scr)
        self.input_area.set_size(lv.pct(100), 60)
        self.input_area.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.input_area.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
        self.input_area.set_style_pad_all(20, 0)
        self.input_area.set_style_radius(0, 0)
        self.input_area.set_style_border_width(1, 0)
        self.input_area.set_style_border_color(lv.color_hex(0xDDDDDD), 0)
        self.input_area.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.ta = lv.textarea(self.input_area)
        self.ta.set_size(lv.pct(80), 44)
        self.ta.align(lv.ALIGN.LEFT_MID, 5, 0)
        self.ta.set_placeholder_text("可以使用语音输入中文")
        self.ta.set_one_line(False)
        self.ta.set_style_bg_color(COLOR_INPUT_BG, 0)
        self.ta.set_style_radius(22, 0)
        self.ta.set_style_pad_all(10, 0)
        self.ta.set_cursor_click_pos(True)
        self.ta.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.send_btn = lv.btn(self.input_area)
        self.send_btn.set_size(lv.pct(10), 44)
        self.send_btn.align_to(self.ta, lv.ALIGN.OUT_RIGHT_MID, 8, 0)
        self.send_btn.set_style_bg_color(lv.color_hex(0x00a5fd), 0)
        self.send_btn.set_style_radius(40, 0)
        self.send_label = lv.label(self.send_btn)
        self.send_label.set_text(lv.SYMBOL.GPS)
        self.send_label.center()
        self.ta.add_event(self.on_textarea_clicked, lv.EVENT.CLICKED, None)
        self.ta.add_event(self.on_textarea_focused, lv.EVENT.FOCUSED, None)
        self.send_btn.add_event(self.on_send_clicked, lv.EVENT.CLICKED, None)
        self.send_btn.add_flag(lv.obj.FLAG.CLICKABLE)
        pass

    def on_textarea_focused(self, evt):
        pass
        try:
            self.keyboard_mgr.show()
            lv.timer_create(self.delayed_scroll_to_bottom, 50, None)
            pass
        except Exception as e:
            pass
            pass

    def delayed_scroll_to_bottom(self, timer):
        self.scroll_to_bottom()
        timer._del()

    def on_textarea_clicked(self, evt):
        pass
        try:
            self.keyboard_mgr.show()
            self.scroll_to_bottom()
            pass
        except Exception as e:
            pass
            pass

    def hide_keyboard(self, evt):
        pass
        try:
            self.keyboard_mgr.hide()
            lv.timer_create(self.delayed_scroll_to_bottom, 50, None)
            pass
        except Exception as e:
            pass
            pass

    def on_send_clicked(self, evt):
        pass
        try:
            msg_text = self.ta.get_text()
            pass
            if msg_text.strip() != "":
                self.add_message(msg_text, True)
                time.sleep_us(1)
                self.add_message("I am thinking ...", False)
                time.sleep_us(1)
                _thread.start_new_thread(self.chat, (msg_text,))
                self.ta.set_text("")
                if self.keyboard_mgr.keyboard_visible:
                    pass
                    self.hide_keyboard(None)
            pass
        except Exception as e:
            pass
            pass

    def chat(self, text):
        try:
            # 配置请求参数
            headers = {
                "Content-Type": "application/json"
            }

            # 构建消息数组
            messages = []

            # 添加历史对话记录
            for text, is_self in self.chat_history:
                if is_self:
                    messages.append({
                        "role": "user",
                        "content": text
                    })
                else:
                    # 跳过 "I am thinking ..." 消息
                    if text != "I am thinking ..." and text != "正在思考中 ...":
                        messages.append({
                            "role": "assistant",
                            "content": text
                        })

            # 调用YbRequests的chat方法获取响应
            response = urequests.chat(chat_url, messages, headers=headers, timeout=60)

            print(response)

            # 更新UI显示
            if response:
                # 移除"thinking"消息
                self.chat_list.get_child(self.chat_list.get_child_cnt() - 1).delete()
                # 添加AI的回复
                self.add_message(response[1], False)
            else:
                # 处理错误情况
                thinking_msg_index = self.chat_list.get_child_cnt() - 1
                self.chat_list.get_child(thinking_msg_index).delete()
                self.add_message("抱歉，我暂时无法回答，请稍后再试。", False)

            # 滚动到底部
            self.scroll_to_bottom()
            return response

        except Exception as e:
            print("Chat error:", e)
            # 处理错误情况
            thinking_msg_index = self.chat_list.get_child_cnt() - 1
            self.chat_list.get_child(thinking_msg_index).delete()
            self.add_message("发生错误，请稍后重试。", False)
            self.scroll_to_bottom()
            response = (False, e)
            return response

    def delete_last_message(self):
        try:
            # 检查是否有消息可以删除
            if not self.chat_history:
                print("没有消息可以删除")
                return False

            # 获取聊天列表中的最后一个子对象（即最后一个消息项）
            chat_list_children = self.chat_list.get_child_cnt()
            if chat_list_children <= 0:
                print("聊天列表中没有消息项")
                return False

            # 获取最后一个消息项
            last_item = self.chat_list.get_child(chat_list_children - 1)
            if last_item is None:
                print("无法获取最后一个消息项")
                return False

            # 从历史记录中移除最后一条消息
            self.chat_history.pop()

            # 删除UI中的消息项
            last_item.delete()

            # 刷新滚动条位置
            lv.timer_create(self.delayed_scroll_to_bottom, 50, None)

            return True
        except Exception as e:
            print("删除最后一条消息时出错:", e)
            return False


    def add_message(self, text, is_self):
        pass
        try:
            item = lv.obj(self.chat_list)
            item.set_width(lv.pct(100))
            item.set_style_bg_opa(0, 0)
            item.set_style_border_width(0, 0)
            item.set_style_pad_all(0, 0)
            item.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
            item.clear_flag(lv.obj.FLAG.SCROLLABLE)
            content_width = self.chat_list.get_content_width()
            max_width = int(content_width * 0.45)
            font_height = 16
            line_space = 2
            temp_label = lv.label(self.scr)
            temp_label.set_text("我")
            temp_label.set_style_text_font(temp_label.get_style_text_font(0), 0)
            temp_label.refr_size()
            char_width = temp_label.get_width()
            temp_label.set_text("")
            if len(text) > 0:
                chars_per_line = max(1, int((max_width - 20) / (char_width+1)))
                lines = text.split('\n')
                estimated_lines = 0
                for line in lines:
                    if line:
                        line_count = max(1, (len(line) + chars_per_line - 1) // chars_per_line)
                        estimated_lines += line_count
                    else:
                        estimated_lines += 1
            else:
                estimated_lines = 1
            temp_label.add_flag(lv.obj.FLAG.HIDDEN)
            temp_label.delete()
            bubble = lv.obj(item)
            bubble.set_style_radius(15, 0)
            bubble.set_style_pad_all(10, 0)
            bubble.clear_flag(lv.obj.FLAG.SCROLLABLE)
            bubble.set_style_bg_color(COLOR_SELF_MSG if is_self else COLOR_OTHER_MSG, 0)
            msg_label = lv.label(bubble)
            msg_label.set_style_text_color(COLOR_TEXT, 0)
            msg_label.set_long_mode(lv.label.LONG.WRAP)
            msg_label.set_text(text)
            msg_label.set_width(min(max_width, char_width * len(text)))
            msg_label.refr_size()
            msg_label.refr_pos()
            label_width = msg_label.get_width()
            bubble_height = max(font_height, font_height * estimated_lines + line_space * (estimated_lines*4 - 10))
            bubble_height += 20
            bubble.set_size(label_width + 20, bubble_height)
            bubble.refr_size()
            bubble.refr_pos()
            bubble.align(lv.ALIGN.TOP_RIGHT if is_self else lv.ALIGN.TOP_LEFT, -5 if is_self else 5, 0)
            msg_label.center()
            item.set_height(bubble.get_height() + 10)
            self.chat_history.append((text, is_self))
            lv.timer_create(self.delayed_scroll_to_bottom, 50, None)
            pass
        except Exception as e:
            print(e)
            pass

    def scroll_to_bottom(self):
        pass
        try:
            if self.chat_list.get_child_cnt() > 0:
                scroll_target = self.chat_list.get_scroll_bottom() * 2
                self.chat_list.scroll_to_y(scroll_target, lv.ANIM.ON)
                pass
            else:
                pass
        except Exception as e:
            pass
            pass



def create_chat_app(recorder=None):
    global chat_app
    pass
    chat_app = ChatUI(recorder=recorder)
    pass
    return chat_app


def async_get_voice_to_text():
    global voice_text_ret
    voice_text_ret = None
    ret = urequests.voice_to_text(f"http://{IP}:3001/voice-to-text", "/sdcard/rec.wav")
    if ret[0]:
        voice_text_ret = ret[1]
    else:
        voice_text_ret = ""

record_flag = False
key = YbKey()

def async_record():
    global recorder,record_flag
    record_flag = False
    recorder.record_with_button("/sdcard/rec.wav", key)
    record_flag = True

def voice_serv():
    global recorder,voice_text_ret,record_flag
    spk = YbSpeaker()
    spk.enable()
    save_path = "/data/audio/"
    # 目录不存在时创建 / create if not exist
    ensure_dir(save_path)

    print("正在初始化录音组件 ...")
    # 按键控制录音，按下开始，松开停止
    while True:
        rgb.show_rgb((0, 255, 0))
        record_flag = False
        _thread.start_new_thread(async_record, ())
        while record_flag==False:
            time.sleep_ms(5)
        time.sleep_ms(5)
        rgb.show_rgb((0, 0, 255))

        # 开始识别
        async_get_voice_to_text()

        while voice_text_ret is None:
            time.sleep_ms(5)

        if voice_text_ret is None or voice_text_ret.strip() == "":
            print("未识别到语音", voice_text_ret)
            recorder.play_audio("/sdcard/utils/sayagain.wav")
            time.sleep_ms(5)
            continue

        chat_app.add_message(voice_text_ret, True)
        time.sleep_ms(5)

        # STEP2 文字问答
        chat_app.add_message("正在思考中 ...", False)
        res = chat_app.chat(voice_text_ret)
        if res[0] == True:
            # 开始文字转语音
            time.sleep_ms(5)
            success = urequests.text_to_speech(f"http://{IP}:3001/text-to-speech", res[1], "/sdcard/reply.wav")
            time.sleep_ms(5)
            try:
                if success:
                    recorder.play_audio("/sdcard/reply.wav")
                    os.remove("/sdcard/reply.wav")
                else:
                    recorder.play_audio("/sdcard/utils/saywhat.wav")
            except Exception as e:
                print(e)
                recorder.play_audio("/sdcard/utils/saywhat.wav")

        # if text:
        #     time.sleep_ms(5)
        #     success = urequests.text_to_speech(f"http://{IP}:3001/text-to-speech", text, "/sdcard/reply.wav")
        #     time.sleep_ms(5)
        #     try:
        #         recorder.play_audio("/sdcard/reply.wav")
        #         os.remove("/sdcard/reply.wav")
        #     except Exception as e:
        #         print(e)
        #         recorder.play_audio("/sdcard/utils/saywhat.wav")
        # else:
        #     recorder.play_audio("/sdcard/utils/saywhat.wav")
        # img2.clear()
        # Display.show_image(img2, 0, 0, Display.LAYER_OSD3)
        # rgb.show_rgb((0, 0, 0))


def main():
    pass
    os.exitpoint(os.EXITPOINT_ENABLE)
    try:
        print(network_use_wlan("11111", "88888888"))
        # network_use_wlan("your_wifi_ssid", "your_password")
        display_init()
        lvgl_init()
        app = create_chat_app(recorder=None)
        _thread.start_new_thread(voice_serv, ())
        print("Voice service started.")
        while True:
            time_ms = lv.task_handler()
            gc.collect()
            time.sleep_ms(time_ms)
    except BaseException as e:
        pass
        pass
    finally:
        pass
        lvgl_deinit()
        display_deinit()
        gc.collect()
        pass


SAMPLE_RATE = 16000         # 采样率 24000Hz，即每秒采样24000次 / Sample rate 24000Hz, i.e., 24000 samples per second
CHANNELS = 1                # 通道数，1为单声道 / Number of channels, 1 for mono
FORMAT = paInt16            # 音频输入输出格式 / Audio input/output format
CHUNK = int(0.3 * 24000)    # 每次读取音频数据的帧数，设置为0.3秒的帧数 / Number of frames to read each time, set to 0.3 seconds of frames
# 初始化音频流 / Initialize audio stream
rgb = YbRGB()
buzzer = YbBuzzer()
# uart = None
DISPLAY_WIDTH = ALIGN_UP(640, 16)
DISPLAY_HEIGHT = 480
IP = "10.159.242.127"
chat_url = f"http://{IP}:3001/chat"
chat_app = None
recorder = AudioRecorder()
voice_text_ret = None


if __name__ == "__main__":
    main()
