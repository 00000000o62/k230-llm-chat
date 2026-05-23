# K230 按键录音 → LLM → 语音播报 (DashScope 直连方案)
# 按下按键录音，松开停止 → Qwen-Audio 理解语音 → Qwen3-TTS-Flash 播报回复
import uos
import time
import gc
import ujson as json
from media.media import *
from media.pyaudio import *
import media.wave as wave
from ybUtils.YbSpeaker import YbSpeaker
from ybUtils.YbKey import YbKey

import YbRequests as requests

# ============================================================
# 配置区 - 使用前请修改
# ============================================================
WIFI_SSID = "11111"
WIFI_KEY = "88888888"
API_KEY = "sk-7f1f0e35b05d44239b6eefa43cff1996"

# ============================================================
# 全局对象
# ============================================================
spk = YbSpeaker()
media_initialized = False

TTS_OUTPUT = "/sdcard/tts_reply.wav"
REC_DIR = "/sdcard/"


def connect_wifi():
    print("Connecting to WiFi...")
    import network
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        print(f"WiFi already connected, IP: {wlan.ifconfig()[0]}")
        return True
    wlan.connect(WIFI_SSID, WIFI_KEY)
    timeout = 15
    while not wlan.isconnected() and timeout > 0:
        time.sleep(1)
        timeout -= 1
        print(f"  waiting... {timeout}s")
    if wlan.isconnected():
        print(f"WiFi connected, IP: {wlan.ifconfig()[0]}")
        return True
    print("WiFi connection timeout!")
    return False


def init_media():
    global media_initialized
    if not media_initialized:
        MediaManager.init()
        media_initialized = True
        print("MediaManager initialized")


def record_until_release(key, filename):
    """按住录音，松开停止，保存为WAV"""
    FORMAT = paInt16
    CHANNELS = 1
    RATE = 44100
    CHUNK = RATE // 25

    print("  Press button to start recording...")
    while not key.is_pressed():
        time.sleep_ms(10)

    frames = []
    p = PyAudio()
    p.initialize(CHUNK)

    init_media()

    input_stream = p.open(
        format=FORMAT, channels=CHANNELS, rate=RATE,
        input=True, frames_per_buffer=CHUNK
    )
    input_stream.volume(LEFT, 85)
    input_stream.volume(RIGHT, 85)

    print("  Recording... (release to stop)")
    while key.is_pressed():
        try:
            frames.append(input_stream.read())
        except Exception as e:
            print(f"  read error: {e}")
            break
        time.sleep_ms(10)

    print("  Recording stopped.")
    input_stream.stop_stream()
    input_stream.close()
    gc.collect()

    print(f"  Frames captured: {len(frames)}")
    if not frames:
        print("  No audio recorded! (hold button longer)")
        return False

    wf = wave.open(filename, 'wb')
    wf.set_channels(CHANNELS)
    wf.set_sampwidth(p.get_sample_size(FORMAT))
    wf.set_framerate(RATE)
    wf.write_frames(b''.join(frames))
    wf.close()

    time.sleep_ms(100)

    try:
        fsize = uos.stat(filename)[6]
        print(f"  Saved: {filename} ({fsize} bytes)")
    except OSError:
        print(f"  WARNING: stat failed for {filename}, continuing anyway")

    gc.collect()
    return True


def upload_audio(filename):
    """上传音频到DashScope OSS (直接HTTP实现，不依赖libs.upload_image)"""
    print("  Uploading audio to OSS...")
    gc.collect()

    for attempt in range(3):
        try:
            # Step 1: 获取OSS上传凭证
            policy_url = ("https://dashscope.aliyuncs.com/api/v1/uploads"
                          "?action=getPolicy&model=qwen-audio-turbo")
            policy_headers = {"Authorization": f"Bearer {API_KEY}"}

            resp = requests.get(policy_url, headers=policy_headers, timeout=30)
            if resp.status_code != 200:
                print(f"  getPolicy failed: {resp.status_code} {resp.text[:100]}")
                continue

            policy = resp.json()["data"]
            gc.collect()

            # Step 2: 构建multipart上传到OSS
            file_name = filename.split("/")[-1]
            key = f"{policy['upload_dir']}/{file_name}"

            with open(filename, "rb") as f:
                file_data = f.read()

            boundary = "----FormBoundary7MA4YWxkTrZu0gW"
            fields = {
                "OSSAccessKeyId": policy["oss_access_key_id"],
                "Signature": policy["signature"],
                "policy": policy["policy"],
                "x-oss-object-acl": policy["x_oss_object_acl"],
                "x-oss-forbid-overwrite": policy["x_oss_forbid_overwrite"],
                "key": key,
                "success_action_status": "200"
            }

            parts = []
            for name, value in fields.items():
                parts.append(
                    "--" + boundary + "\r\n"
                    "Content-Disposition: form-data; name=\"" + name + "\"\r\n"
                    "\r\n" + value + "\r\n"
                )
            parts.append(
                "--" + boundary + "\r\n"
                "Content-Disposition: form-data; name=\"file\"; filename=\"" + file_name + "\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n"
            )

            text_bytes = "".join(parts).encode("utf-8")
            end_bytes = f"\r\n--{boundary}--\r\n".encode("utf-8")
            body = text_bytes + file_data + end_bytes

            upload_headers = {
                "Content-Type": f"multipart/form-data; boundary={boundary}"
            }

            resp = requests.post(
                policy["upload_host"],
                data=body, headers=upload_headers, timeout=60
            )

            if resp.status_code == 200:
                oss_url = f"oss://{key}"
                print(f"  OSS URL: {oss_url}")
                return oss_url
            else:
                print(f"  OSS post failed: {resp.status_code}")

        except Exception as e:
            print(f"  Upload attempt {attempt + 1} failed: {e}")
            gc.collect()
            if attempt < 2:
                time.sleep(1)

    print("  Upload failed after retries!")
    return None


def ask_qwen_audio(oss_url):
    """调用Qwen-Audio模型，直接理解语音内容"""
    print("  Asking Qwen-Audio...")
    gc.collect()

    url = ("https://dashscope.aliyuncs.com/api/v1/services/"
           "aigc/multimodal-generation/generation")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-OssResourceResolve": "enable"
    }
    body = {
        "model": "qwen-audio-turbo-latest",
        "input": {
            "messages": [
                {"role": "system",
                 "content": [{"text": "You are a helpful assistant."}]},
                {"role": "user",
                 "content": [{"audio": oss_url}]}
            ]
        }
    }

    resp = requests.post(url, headers=headers, json_data=body, timeout=60)
    print(f"  Qwen-Audio status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"  API error: {resp.text[:200]}")
        return None

    try:
        raw = resp.text if isinstance(resp.text, str) else resp.text.decode('utf-8')
        result = json.loads(raw)
        choices = result["output"]["choices"]
        if choices:
            content = choices[0]["message"]["content"]
            if content and "text" in content[0]:
                reply = content[0]["text"]
                print(f"  AI reply: {reply}")
                return reply
    except Exception as e:
        print(f"  Parse error: {e}")
    return None


def text_to_speech(text, voice="Cherry"):
    """调用Qwen3-TTS-Flash将文字转为语音"""
    print(f"  TTS: {text[:40]}...")
    gc.collect()

    url = ("https://dashscope.aliyuncs.com/api/v1/services/"
           "aigc/multimodal-generation/generation")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "qwen3-tts-flash",
        "input": {
            "text": text,
            "voice": voice,
            "language_type": "Chinese"
        }
    }

    resp = requests.post(url, headers=headers, json_data=body, timeout=60)
    if resp.status_code != 200:
        print(f"  TTS API error: {resp.status_code}")
        return False

    try:
        raw = resp.text if isinstance(resp.text, str) else resp.text.decode('utf-8')
        result = json.loads(raw)
        audio_url = result["output"]["audio"]["url"]
        print(f"  TTS audio URL ready")
    except Exception as e:
        print(f"  TTS parse error: {e}")
        return False

    print("  Downloading TTS audio...")
    audio_resp = requests.get(audio_url, timeout=30)
    if audio_resp.status_code != 200:
        print(f"  Download failed: {audio_resp.status_code}")
        return False

    with open(TTS_OUTPUT, 'wb') as f:
        f.write(audio_resp.content)
    print(f"  TTS saved: {TTS_OUTPUT}")
    return True


def play_audio(filename):
    """播放WAV音频"""
    try:
        with open(filename, 'rb') as f:
            pass
    except OSError:
        print(f"  Audio file not found: {filename}")
        return

    print(f"  Playing: {filename}")
    try:
        spk.enable()
        wf = wave.open(filename, 'rb')
        CHUNK = int(wf.get_framerate() / 25)

        p = PyAudio()
        p.initialize(CHUNK)

        stream = p.open(
            format=p.get_format_from_width(wf.get_sampwidth()),
            channels=wf.get_channels(),
            rate=wf.get_framerate(),
            output=True,
            frames_per_buffer=CHUNK
        )
        stream.volume(vol=100)

        data = wf.read_frames(CHUNK)
        while data:
            stream.write(data)
            data = wf.read_frames(CHUNK)

    except Exception as e:
        print(f"  Play error: {e}")
    finally:
        try:
            stream.stop_stream()
            stream.close()
            p.terminate()
            wf.close()
            spk.disable()
        except:
            pass
    print("  Playback done.")


def cleanup(path):
    try:
        uos.remove(path)
        gc.collect()
    except:
        pass


def main():
    print("=" * 50)
    print("K230 Voice Chat - DashScope")
    print("Press button to record, release to send")
    print("=" * 50)

    if not connect_wifi():
        print("WiFi failed! Check SSID/KEY.")
        return

    key = YbKey()
    count = 0

    while True:
        rec_file = ""
        try:
            count += 1
            print(f"\n--- Conversation #{count} ---")

            rec_file = REC_DIR + "voice_" + str(time.ticks_ms()) + ".wav"

            if not record_until_release(key, rec_file):
                cleanup(rec_file)
                print("  Recording failed, retry...")
                continue

            oss_url = upload_audio(rec_file)
            cleanup(rec_file)
            if not oss_url:
                print("  Upload failed, retry...")
                continue

            reply = ask_qwen_audio(oss_url)
            if not reply:
                print("  No reply from LLM.")
                continue

            if not text_to_speech(reply):
                print("  TTS failed.")
                continue

            play_audio(TTS_OUTPUT)
            cleanup(TTS_OUTPUT)

            print(f"--- Conversation #{count} done ---")

        except KeyboardInterrupt:
            print("\nUser interrupted.")
            break
        except Exception as e:
            print(f"  Conversation error: {e}")
            cleanup(rec_file)
            cleanup(TTS_OUTPUT)
            time.sleep(1)

    print(f"Finished. {count} conversations completed.")


if __name__ == "__main__":
    main()
