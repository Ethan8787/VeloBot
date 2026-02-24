# VeloBot

簡介
----
VeloBot 是一個用於 Discord 的機器人，主要提供 Minecraft 伺服器狀態查詢、代理伺服器 IP 狀態檢查、以及一些好玩的回應指令。程式以 Python 撰寫，使用 discord.py、mcstatus 與其他網路工具。

功能
----
- 查詢 Minecraft 伺服器狀態（MOTD、玩家數、版本、延遲）
- 顯示代理伺服器（proxy）是否上線
- DNS / GeoIP / ASN 查詢與 tracert 輸出
- Bot latency 測試
- 同步 Slash commands 與傳統前綴命令（`status`、`ip`、`ping` 等，前綴為 `.`）

相依套件
----
依賴列在 requirements.txt，主要包括：
- discord.py
- aiohttp
- dnspython
- psutil
- python-dotenv
- mcstatus
- requests

快速開始
----
1. 建議使用虛擬環境：
   - python -m venv .venv
   - Windows：.venv\Scripts\activate
   - Unix/macOS：source .venv/bin/activate

2. 安裝依賴：
   - pip install -r requirements.txt

3. 設定檔：
   - config.json（範例鍵）
     - role_id: 要監控或使用的角色 ID（陣列）
     - proxy_ip: 要檢查的 Minecraft 代理主機（字串，例如 example.com）
     - channel_id: 要自動改名的頻道 ID（整數）
     - cache_seconds: 狀態快取時間（秒）
   - .env（你需要自己創建並放在專案目錄下）
     - BOT_TOKEN: Discord Bot Token

4. 啟動：
   - python velo_bot.py