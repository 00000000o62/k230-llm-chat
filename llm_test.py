from ybUtils.LLM import *

def network_use_wlan(ssid, key):
    import network
    sta = network.WLAN(0)
    sta.connect(ssid, key)
    while not sta.isconnected():
        time.sleep(1)
    return sta.ifconfig()[0]
# 测试代码
if __name__ == "__main__":

    # 连接网络
    print("等待连接网络 waiting connect to wifi")
    network_use_wlan("11111", "88888888")

    # Spark示例
    spark_api_key = "your-openrouter-api-key"

    print("正在等待响应 ...")
    simple_chat_example(
        api_key=spark_api_key,
        prompt="给我唱首歌吧",
        model_type=openrouter,
        model="deepseek/deepseek-chat-v3-0324"
    )
