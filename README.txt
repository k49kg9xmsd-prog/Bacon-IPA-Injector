Bacon IPA Injector — 本機瀏覽器版 / 簡潔介面

本版與 baconclicker-core 類似，不需要 Render、Python、伺服器網址或密碼。
在瀏覽器使用內建的 JSZip + Mach-O LC_LOAD_DYLIB 修改邏輯。
所有 IPA 和 DYLIB 只在使用者裝置記憶體中處理，不上傳任何伺服器。

部署到 GitHub Pages：
1. 前往 https://github.com/k49kg9xmsd-prog/Bacon-IPA-Injector
2. 將 ZIP 裡的 index.html 取代儲存庫根目錄的 index.html。
3. 若 Pages 使用 main /docs，也同時用 docs/index.html 取代原來的 docs/index.html。
4. GitHub Settings > Pages 設定 main / (root) 或 main /docs，保持與上述檔案位置相同。
5. 開啟 https://k49kg9xmsd-prog.github.io/Bacon-IPA-Injector/

支援：
- 單一 .ipa + 單一 ARM64 Mach-O .dylib
- IPA 未經 FairPlay 加密，主程式具足夠 load-command 空間
- 輸出 -Injected-Unsigned.ipa，需自己重新簽名

限制：
- 本版不支援 .deb、加密 IPA、缺少架構 / 載入指令空間、依賴外部 Framework 的插件
- JSZip 需使用相對多的裝置記憶體；處理大檔案時 Safari 可能中止或重新整理
- 插件注入不代表能正常運作，插件還需要與 App / iOS 相容
- 請僅修改自己有權修改的 App 與可信插件

單一 index.html 已包含 JSZip v3.10.1，無 CDN、無遠端 API。
JSZip 授權見 LICENSE-JSZIP.txt。
