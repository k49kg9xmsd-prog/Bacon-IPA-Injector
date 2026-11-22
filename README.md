# 🥓 Bacon IPA Injector

**一個可以自己架設的網頁：上傳 `.ipa` + `.dylib` → 產生已注入的 `.ipa`。**

第一版支援：單一 arm64 `.dylib` 注入、IPA 基礎驗證、檔案拖曳上傳、進度顯示、輸出檔下載。使用開源 `zsign` 修改主程式的動態庫載入指令、嵌入插件、重新封裝並作 **ad-hoc 暫時簽章**。不蒐集 P12 憑證或描述檔。

> 重要：**產出的 IPA 不代表能直接安裝。** 仍需在 ESign、KSign 或其他合法簽名流程中依你的設備與憑證重簽。這不是 iOS 漏洞或 Apple 驗證繞過工具。DRM/FairPlay 加密 IPA 不支援；注入成功也不保證插件能載入或正常運作。僅使用你有權修改的 App 和可信插件。

## GitHub Pages + Render 雲端部署（推薦給用 GitHub 的人）

**重要**：只把 `/docs` 上傳 GitHub Pages 只能顯示介面，**無法直接注入**。GitHub Pages 不執行 Python 或 `zsign`。本專案把靜態介面部署在 GitHub Pages，再透過 HTTPS 連接 Render 的 Docker 後端。

1. **建立 GitHub Repository**，將本 ZIP 解壓後的**檔案和資料夾本身**推送至儲存庫根目錄。**不要提交任何真實 IPA、dylib、簽名憑證或私密密碼。**
2. 在儲存庫 **Settings → Pages → Build and deployment → Deploy from a branch**，選擇 `main`、`/docs`，再按 **Save**。首頁會在 `https://你的帳號.github.io/你的儲存庫/`（若儲存庫名字剛好是 `<username>.github.io` 則是根網域）。
3. 註冊 <https://render.com/>，使用 **New → Blueprint** 連接同一個 GitHub Repository，讓 Render 使用根目錄的 `render.yaml` 部署（也可選 New → Web Service → Docker）。Render 免費方案會休眠，且記憶體/磁碟資源有限，大 IPA 不適合免費方案。
4. 在 Render 設定環境變數：`APP_PASSWORD` 為**非空白、強密碼**；`CORS_ORIGINS` 為 `https://你的帳號.github.io`，注意**只填來源網域，不包含儲存庫路徑**。如果使用自訂網域，改填或逗號分隔加入你的自訂網域來源。部署完成後確認 `https://你的服務.onrender.com/api/health` 有回應。
5. GitHub 編輯 `docs/config.js`，把 `window.BACON_API_BASE = '';` 改為 `window.BACON_API_BASE = 'https://你的服務.onrender.com';`。URL 必須是你自己實際拿到的網址（不要照抄例子）。Commit 後重新整理你的 GitHub Pages。
6. 手機 Safari 打開 GitHub Pages；右上角應顯示「注入引擎已就緒」。上傳 IPA 與 dylib、輸入網站密碼、注入並下載結果。

**注意**：網站密碼只能放在 Render 環境變數，**不能**寫進公開的 `docs/config.js`、GitHub Repository 或其他前端檔案。`CORS_ORIGINS` 不是身分驗證，網站密碼也只是基本保護，公開給其他人使用前仍要評估上傳限額、DoS、執行隔離、速率限制和隱私風險。

**手機上傳大型檔案**：Render Free 實例資源有限（免費方案可休眠，只有 512 MB RAM），不保證大 IPA 能處理；建議先以你自己有權修改的小型測試 IPA 驗證。

## 最快啟動：Docker

需求：電腦或 VPS（Windows、Linux、macOS）已安裝 Docker。第一次建置需連接 GitHub 下載並編譯 zsign。

```bash
cd BaconIPAInjector
# 可選：設定網站存取密碼。公開服務務必啟用密碼及 HTTPS。
# Linux/macOS:
export APP_PASSWORD='你的私人網站密碼'
docker compose up --build -d
```

瀏覽器打開 **http://127.0.0.1:8000**。目前 docker-compose 預設**只綁本機**，不會直接暴露於公網。

Windows PowerShell 設定密碼：`$env:APP_PASSWORD="你的私人網站密碼"`。也可不設密碼僅供本機自己使用。

## 不使用 Docker（Windows / Linux / macOS）

1. 安裝 Python 3.11+ 與 `zsign` CLI；zsign 官方專案：<https://github.com/zhlynn/zsign>（依作業系統編譯，並將執行檔加入 PATH）。
2. 在此專案資料夾執行：

```bash
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

3. 到 `http://127.0.0.1:8000` 使用。Windows 也可在 zsign 與 Python 配置完成後，雙擊 `start-windows.bat`；macOS/Linux 可執行 `bash start-mac-linux.sh`。

若 zsign 不在 PATH，可設定 `ZSIGN_PATH` 為可執行檔完整路徑。首頁右上角會顯示引擎是否就緒。

## 實際注入流程

```text
上傳 IPA + dylib
  ↓
檢查副檔名／大小／ZIP 結構／Info.plist／arm64 Mach-O
  ↓
zsign -a -l 插件.dylib -o output.ipa input.ipa
  ↓
檢查輸出 ZIP 是否包含插件
  ↓
提供 30 分鐘的隨機下載 URL
  ↓
自行使用簽名工具重新簽名後側載
```

## 重要限制

- 僅支援 **一個 `.dylib`**，暫不支援 `.deb`、`.framework`、插件依賴庫或 Substrate/ElleKit 自動補齊。
- 只修改 **主 App 的載入**；App Extension 不會自動注入。
- 插件與 App 需要可相容的架構／框架／環境；僅驗證 ARM64 Mach-O 入口，**不保證**內部所有依賴和簽名限制都通過。
- App Store 取得且未解密的 FairPlay IPA 不適用。上傳前需使用有權修改的、未加密的 IPA。
- 輸出為 ad-hoc 簽章，**不等於可直接安裝到非越獄設備**；安裝前必須透過與目標裝置相容的方式重新簽章。
- 舊的 `.dylib` 可能需額外 hook framework，單純載入並不等於會運作。
- 大型 IPA 需要充足空間，預留至少 **3～4 倍 IPA 大小**；處理逾時預設 10 分鐘。

## 資安與部署

- 後端只呼叫 `zsign`，不會執行上傳的 IPA 或 dylib；**但解析惡意二進位仍有風險**。只處理信任的檔案，建議在低權限容器及私有網路執行。
- **不要直接公開無密碼網址**：需額外設定 HTTPS、反向代理上傳上限、驗證、存取速率限制與隔離防護。`APP_PASSWORD` 只提供最簡單的注入請求密碼保護，並非完整公開平台的權限系統。
- 輸入檔在處理成功後立即刪除；成功輸出 30 分鐘過期自動刪除；處理失敗立即清理。伺服器異常關閉可能留下暫存檔，需自行清理工作目錄（預設 `/tmp/bacon-ipa-injector`）。
- 資料在網路上傳給**你部署的伺服器**；這不是在手機瀏覽器裡完全本機處理。若上網公開，請務必使用 HTTPS。
- 下載網址持有者可下載結果，請勿分享連結。部署時請限制訪客使用。
- 目前預設 `--workers 1`，因下載暫存資訊保存在單一進程記憶體。多進程需外部共享 job store。
- 開發環境也不要提交真實 IPA／dylib／簽名憑證至版本控制。

## 可調環境變數

| 名稱 | 預設 | 說明 |
| --- | --- | --- |
| `ZSIGN_PATH` | `zsign` | zsign 執行檔 |
| `APP_PASSWORD` | 空白 | 非空時要求網站存取密碼 |
| `MAX_IPA_MB` | `2048` | IPA 單檔上限（MB） |
| `MAX_PLUGIN_MB` | `32` | dylib 單檔上限（MB） |
| `MAX_UNPACKED_MB` | `12288` | ZIP 解壓內容上限（MB） |
| `WORK_DIR` | 系統暫存資料夾 | 用來存工作目錄的上層資料夾 |
## 開發測試

```bash
python -m pip install pytest httpx
python -m pytest -q
```

測試會模擬 zsign 的檔案輸出與錯誤情形；**不等於實機成功注入測試**，部署時請以你有權修改的測試 App 與對應插件進行端對端測試。

## 授權與依賴

本站範例代碼供修改使用。第三方 `zsign` 由原作者維護，依其專案 MIT License 使用：<https://github.com/zhlynn/zsign>。

| `CORS_ORIGINS` | 空白 | 允許呼叫 API 的 GitHub Pages 來源網域，可逗號分隔 |
