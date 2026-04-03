# 二手交易中心 x 7-11 賣貨便

這個專案已整理成可直接上傳 GitHub，並部署到 Streamlit Community Cloud 的版本。

目前功能包含：

- 商品刊登
- 商品照片上傳與顯示
- 關鍵字、分類、狀態篩選
- 7-11 賣貨便連結綁定與跳轉
- 商品狀態切換
- 買家與賣家留言
- 管理模式刪除商品

## GitHub 與 Streamlit 要保留的檔案

- `streamlit_app.py`
- `marketplace_store.py`
- `requirements.txt`
- `README.md`
- `.gitignore`
- `.streamlit/config.toml`
- `.streamlit/secrets.example.toml`

## 資料存放方式

- 商品、留言、照片資料預設會放在 `marketplace.db`
- 商品照片會以 Base64 Data URL 形式存放在 SQLite 的 `photos_json` 欄位

## 部署到 Streamlit Community Cloud

1. 把這個專案上傳到 GitHub
2. 登入 [Streamlit Community Cloud](https://share.streamlit.io/)
3. 選擇你的 GitHub repository
4. Main file path 填入 `streamlit_app.py`
5. 按下 Deploy

## Secrets 設定

如果你要保留「只有你能刪除商品」的能力，請在 Streamlit App 的 Secrets 設定加入：

```toml
ADMIN_DELETE_KEY = "請改成你自己的刪除碼"
```

如果沒有設定，網站仍可使用，但管理功能會停用。

## 本機執行

先安裝 Python 與相依套件：

```bash
pip install -r requirements.txt
```

再執行：

```bash
streamlit run streamlit_app.py
```

## 重要提醒

目前這版仍使用本地 SQLite。

這代表：

- 本機執行時，資料可以正常保留
- 在 Streamlit Community Cloud 上，本地資料不保證永久保留

如果之後要長期正式使用，建議再改成外部資料庫，例如 Supabase Postgres 或 Neon。
