"""
arm_link.py —— 和機械手臂講話的模組 (換手臂只改這一支)

現在的手臂 (上銀 HIWIN HRSS, 大會 script docs/hiwin_flow_v1.hrb) 是這樣講話的:
  手臂當客戶端, 用 COPEN(ETH, 192,168,1,10, 5000) 連到樹莓派的 5000 埠
  手臂 CWRITE "GET" → 線路上是 {GET}   → 我們回 {x,y}: 手臂座標 mm 乘 1000 的整數
                                             (手臂 CREAD 兩個 REAL, 各除 1000 還原成 mm)
  沒有可以給的                             → 回 {0,0} (手臂端判到 0,0 就不移動)
  其他句子: SCAN / GRIP / RELEASE / RESET / QUIT (主程式決定回什麼)

上銀的封包【沒有換行】, 靠起始符號 { 和結尾符號 } 界定, 欄位用 , 分隔。
這三個符號是 HIWIN Robot Software Manual 3.3 第 6.10.2 節 (p.258) 的預設值,
在教導器 Start-up → Network Config 可以改; 改了就要同步改下面的 HEAD / TAIL / SEP。
"""
import socket

HOST, PORT = "0.0.0.0", 5000     # 樹莓派在這個埠等手臂來連 ("0.0.0.0" = 任何網路卡都可)
HEAD, TAIL, SEP = "{", "}", ","  # 封包起始 / 結尾 / 分隔符號 (手冊 6.10.2 p.258 預設值)
SCALE = 1000                     # 座標 mm × SCALE 後取整數送出; 手臂端 script 的 SCALE 要一樣
MAX_BUF = 1024                   # 收了這麼多 bytes 還沒看到結尾符號 → 當垃圾丟掉, 避免緩衝無限長大

# ---------- 手臂會送來的指令字 (線路上是 {GET}, 拆掉框界後就是 GET) ----------
CMD_GET = "GET"
CMD_SCAN = "SCAN"
CMD_GRIP = "GRIP"
CMD_RELEASE = "RELEASE"
CMD_RESET = "RESET"
CMD_QUIT = "QUIT"

# ---------- 我們回給手臂的格式 ----------
# 一律兩個數字欄位: 手臂端只寫一行 CREAD(h, READ1, READ2) 就能收所有回覆。
# (手冊 p.258: 欄位比變數少會補 0、多的忽略, 所以欄位數固定最保險。)
# 手臂 script 只會送 GET; 下面其他回覆是給 nc 手動測試看的。
REPLY_OK = "1,1"                 # GRIP / RELEASE / RESET 的 ack
REPLY_BYE = "-1,-1"              # QUIT
REPLY_NONE = "0,0"               # 沒有可給的物件 (0,0 是手臂基座, 不會是真實物件)


def reply_target(x, y):
    """一件物件的手臂座標, 例: x=487.5, y=-12.3 → 487500,-12300 (上線再包成 {487500,-12300})
    不回顏色: 顏色只是樹莓派用來找中心點的依據, 手臂照 PICK_ORDER 的順序就知道第幾件是什麼。"""
    return f"{int(round(x * SCALE))}{SEP}{int(round(y * SCALE))}"


def reply_count(n):
    """SCAN 的回覆: 快照件數, 第二欄補 0 湊成兩欄。"""
    return f"{n}{SEP}0"


class ArmLink:
    def __init__(self):
        self.srv = None
        self.conn = None
        self.buf = b""

    def open(self):
        """開始等手臂連線 (主程式在快照完成後才呼叫)。"""
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind((HOST, PORT))
        self.srv.listen(1)
        self.srv.settimeout(0.05)       # 每圈最多等 0.05 秒, 不卡住主程式

    def poll(self):
        """收這一圈的指令, 回傳清單 (可能是空的)。每句話拆掉 { }、轉大寫、去頭尾空白。"""
        if self.conn is None:
            try:
                self.conn, addr = self.srv.accept()
                self.conn.settimeout(0.05)
                self.buf = b""
                print(f"[arm] 手臂連線: {addr}")
            except socket.timeout:
                return []
        try:
            data = self.conn.recv(1024)
        except socket.timeout:
            return []
        except OSError:
            self.conn = None
            return []
        if not data:                    # 手臂關了連線 (CCLOSE), 等下一次 COPEN
            self.conn.close()
            self.conn = None
            return []
        self.buf += data

        cmds = []
        head, tail = HEAD.encode(), TAIL.encode()
        while True:                     # 一次可能收到半句或一句半, 看到結尾符號才算一句
            i = self.buf.find(head)
            j = self.buf.find(tail)
            if i == -1 or j == -1 or j < i:
                break
            cmd = self.buf[i + 1:j].decode(errors="ignore").strip().upper()
            self.buf = self.buf[j + 1:]  # 起始符號前面的雜訊一起丟掉
            if cmd:
                cmds.append(cmd)

        if len(self.buf) > MAX_BUF:     # 一直沒有結尾符號 → 對方的封包格式不對 (檢查 Network Config 的 { } ,)
            print(f"[arm] 收到 {len(self.buf)} bytes 都沒有結尾符號 '{TAIL}', 丟掉; 請確認手臂 Network Config 的封包符號")
            self.buf = b""
        return cmds

    def send(self, text):
        """回一句話給手臂 (自動包上 { })。不加換行: 手臂靠 } 判斷封包結束。"""
        try:
            self.conn.sendall((HEAD + text + TAIL).encode())
        except OSError:
            self.conn = None

    def close(self):
        if self.conn:
            self.conn.close()
        if self.srv:
            self.srv.close()
