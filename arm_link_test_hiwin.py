"""
arm_link_test_hiwin.py —— 只測「手臂 ↔ 樹莓派」的通訊 (上銀 HIWIN 版, 廠商測機用)

跟比賽主程式的差別
  不開相機、不讀 vision_profiles.json、不碰 GPIO、不做座標轉換。
  只留下 arm_link.py (和比賽用的是同一支), 所以這裡測通的連線、封包符號、
  座標倍率, 比賽時完全一樣。

手臂送什麼 → 這支回什麼 (線路上都包在 { } 裡, 沒有換行)
  {GET}      → {x,y}    下面 FAKE_TARGETS 的下一個點, 用完自動從頭再來
                        座標是 mm × 1000 的整數, 手臂端 script 會除回來
  {SCAN}     → {n,0}
  {RESET}    → {1,1}    並把取用順序歸零
  {QUIT}     → {-1,-1}
  其他       → {1,1}

執行
  python3 arm_link_test_hiwin.py

賽前手臂端要先確認的三件事
  1. hiwin_flow_v1.hrb 的 COPEN 那一行是 192.168.1.10 : 5000
  2. 樹莓派有線網卡 IP 設成 192.168.1.10/24
  3. 教導器 Start-up → Network Config 的封包符號是 { } , (和 arm_link.py 的 HEAD/TAIL/SEP 一致)

注意
  手臂 script 收到座標會真的移動, FAKE_TARGETS 請填這台手臂上安全可達的點。
  不要填 (0, 0): 這個協定用 {0,0} 代表「沒有可給的物件」, 手臂會判成不移動。
"""
import time

import arm_link

# ======= 測試用假座標 (單位 mm, 手臂座標系) =======
# 這裡只驗通訊, 座標本身不需要準; 但手臂會真的移動過去, 務必填安全的點。
FAKE_TARGETS = [
    (300.0, 0.0),
    (300.0, 60.0),
    (300.0, -60.0),
]
# ================================================


def main():
    link = arm_link.ArmLink()
    link.open()
    print(f"[測試] 開始等手臂連線: {arm_link.HOST}:{arm_link.PORT}")
    print(f"[測試] 假座標共 {len(FAKE_TARGETS)} 個, 用完會從頭再來")
    print(f"[測試] 座標倍率 SCALE = {arm_link.SCALE} (手臂端 script 的 SCALE 要一樣)")
    print("[測試] Ctrl+C 離開\n")

    i = 0                                   # 下一次 GET 要給第幾個假座標 (RESET 會歸零)
    total = 0                               # 這次總共給了幾組 (只增不減, 結尾統計用)
    running = True
    try:
        while running:
            for cmd in link.poll():         # 收這一圈手臂送來的句子 (arm_link 已拆掉 { })
                print(f"[收到] {{{cmd}}}")

                if cmd == arm_link.CMD_GET:
                    x, y = FAKE_TARGETS[i % len(FAKE_TARGETS)]
                    i += 1
                    total += 1
                    reply = arm_link.reply_target(x, y)
                    print(f"       第 {total} 次 GET, 要給 X={x} Y={y} mm")

                elif cmd == arm_link.CMD_SCAN:
                    reply = arm_link.reply_count(len(FAKE_TARGETS))

                elif cmd == arm_link.CMD_RESET:
                    i = 0
                    reply = arm_link.REPLY_OK

                elif cmd == arm_link.CMD_QUIT:
                    reply = arm_link.REPLY_BYE
                    running = False

                else:                       # GRIP / RELEASE / 打錯字都回 ack
                    reply = arm_link.REPLY_OK

                link.send(reply)
                print(f"[回覆] {arm_link.HEAD}{reply}{arm_link.TAIL}")

            time.sleep(0.01)                # 沒事做時稍微讓一下 CPU
    except KeyboardInterrupt:
        print("\n[測試] 手動結束")
    finally:
        link.close()
        print(f"[測試] 已關閉, 這次共給了 {total} 組座標")


if __name__ == "__main__":
    main()
