import base64
import hmac
import html
import io
import os
from datetime import datetime
from urllib.parse import urlparse

import streamlit as st
from PIL import Image, ImageOps

from marketplace_store import (
    add_message,
    create_listing,
    delete_listing,
    get_database_path,
    initialize_database,
    list_listings,
    update_listing_status,
    update_myship_link,
)


st.set_page_config(
    page_title="二手交易中心 x 7-11 賣貨便",
    layout="wide",
)

MYSHIP_HOME_URL = "https://myship.7-11.com.tw/Home/Main"
MYSHIP_CREATE_URL = "https://myship.7-11.com.tw/easy/add"
MAX_PHOTO_COUNT = 5
MAX_MESSAGE_LENGTH = 500
MAX_IMAGE_EDGE = 1600
MAX_DATA_URL_LENGTH = 4_000_000

CATEGORY_LABELS = {
    "all": "全部分類",
    "3C": "3C",
    "furniture": "家具",
    "clothing": "服飾",
    "books": "書籍",
    "sports": "運動",
    "other": "其他",
    "家具": "家具",
    "服飾": "服飾",
    "書籍": "書籍",
    "運動": "運動",
    "其他": "其他",
}

CONDITION_LABELS = {
    "mint": "近全新",
    "good": "良好",
    "fair": "普通",
    "cleanup": "待整理",
    "近全新": "近全新",
    "良好": "良好",
    "普通": "普通",
    "待整理": "待整理",
}

STATUS_LABELS = {
    "all": "全部狀態",
    "available": "可交易",
    "sold": "已售出",
}

ROLE_LABELS = {
    "buyer": "買家",
    "seller": "賣家",
}


@st.cache_resource
def bootstrap_database():
    """Initialize the database once per app session."""
    initialize_database()
    return get_database_path()


def inject_custom_style():
    """Add a light brand layer so the Streamlit page feels intentional."""
    st.markdown(
        """
        <style>
            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(255, 215, 170, 0.45), transparent 28%),
                    linear-gradient(180deg, #f7efe5 0%, #f3e6d7 100%);
            }

            .hero-shell {
                padding: 1.4rem 1.6rem;
                border-radius: 24px;
                background: linear-gradient(135deg, #2d211b 0%, #5b3f2f 55%, #946247 100%);
                color: #fff7ef;
                box-shadow: 0 18px 45px rgba(70, 40, 20, 0.18);
                margin-bottom: 1rem;
            }

            .hero-eyebrow {
                font-size: 0.8rem;
                letter-spacing: 0.18em;
                text-transform: uppercase;
                opacity: 0.78;
            }

            .hero-title {
                font-size: 2rem;
                font-weight: 800;
                margin: 0.35rem 0 0.6rem 0;
            }

            .hero-copy {
                max-width: 780px;
                line-height: 1.7;
                margin: 0;
            }

            .badge-row {
                display: flex;
                flex-wrap: wrap;
                gap: 0.45rem;
                margin: 0.25rem 0 0.85rem 0;
            }

            .market-badge {
                display: inline-flex;
                align-items: center;
                padding: 0.26rem 0.72rem;
                border-radius: 999px;
                background: #efe1cf;
                color: #5d402d;
                font-size: 0.82rem;
                font-weight: 700;
            }

            .market-badge--sold {
                background: #ead0d0;
                color: #8a1f1f;
            }

            .market-badge--available {
                background: #dcebdc;
                color: #21633c;
            }

            .meta-block {
                color: #56463b;
                line-height: 1.75;
                margin-bottom: 0.65rem;
            }

            .message-item {
                border-radius: 16px;
                padding: 0.85rem 1rem;
                margin-bottom: 0.7rem;
                border: 1px solid rgba(99, 66, 45, 0.12);
                background: rgba(255, 250, 244, 0.9);
            }

            .message-item--buyer {
                background: rgba(225, 239, 255, 0.78);
            }

            .message-item--seller {
                background: rgba(245, 229, 212, 0.92);
            }

            .message-header {
                display: flex;
                justify-content: space-between;
                gap: 1rem;
                font-size: 0.9rem;
                color: #694d39;
                margin-bottom: 0.35rem;
            }

            .message-content {
                margin: 0;
                color: #2d211b;
                line-height: 1.65;
                white-space: pre-wrap;
            }

            .listing-empty {
                border-radius: 18px;
                padding: 1.2rem;
                border: 1px dashed rgba(99, 66, 45, 0.22);
                background: rgba(255, 250, 244, 0.7);
                color: #695747;
                text-align: center;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def ensure_session_state():
    """Centralize transient UI state."""
    st.session_state.setdefault("admin_verified", False)
    st.session_state.setdefault("flash_message", "")
    st.session_state.setdefault("flash_level", "success")


def set_flash(message: str, level: str = "success"):
    st.session_state["flash_message"] = message
    st.session_state["flash_level"] = level


def show_flash():
    """Show one-time feedback and then clear it."""
    message = st.session_state.get("flash_message", "")
    if not message:
        return

    level = st.session_state.get("flash_level", "success")
    if level == "error":
        st.error(message)
    elif level == "warning":
        st.warning(message)
    else:
        st.success(message)

    st.session_state["flash_message"] = ""


def get_admin_delete_key() -> str:
    """Read the admin delete key from Streamlit secrets first."""
    secret_value = ""

    try:
        secret_value = str(st.secrets.get("ADMIN_DELETE_KEY", "")).strip()
    except Exception:
        secret_value = ""

    if secret_value:
        return secret_value

    return os.environ.get("ADMIN_DELETE_KEY", "").strip()


def normalize_text(value) -> str:
    return str(value).strip() if value is not None else ""


def validate_myship_url(raw_url: str):
    """Only allow official MyShip links."""
    normalized_url = normalize_text(raw_url)
    if not normalized_url:
        return None, ""

    parsed = urlparse(normalized_url)
    if parsed.scheme != "https" or parsed.netloc != "myship.7-11.com.tw":
        return None, "7-11 賣貨便連結必須使用官方 myship.7-11.com.tw 網址。"

    return normalized_url, ""


def image_to_data_url(uploaded_file) -> str:
    """Resize and encode images before storing them in SQLite."""
    uploaded_file.seek(0)
    image = Image.open(uploaded_file)
    image = ImageOps.exif_transpose(image)
    image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))

    has_alpha = "A" in image.getbands()
    buffer = io.BytesIO()

    if has_alpha:
        image.save(buffer, format="PNG", optimize=True)
        mime_type = "image/png"
    else:
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.save(buffer, format="JPEG", quality=85, optimize=True)
        mime_type = "image/jpeg"

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded}"

    if len(data_url) > MAX_DATA_URL_LENGTH:
        raise ValueError("照片壓縮後仍然過大，請改用尺寸較小的圖片。")

    return data_url


def decode_data_url(data_url: str):
    """Decode a stored image for display."""
    if not data_url or "," not in data_url:
        return None

    encoded_value = data_url.split(",", 1)[1]

    try:
        return base64.b64decode(encoded_value)
    except (ValueError, TypeError):
        return None


def format_category(value: str) -> str:
    return CATEGORY_LABELS.get(value, value)


def format_condition(value: str) -> str:
    return CONDITION_LABELS.get(value, value)


def format_status(value: str) -> str:
    return STATUS_LABELS.get(value, value)


def format_datetime(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace(" ", "T"))
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def render_hero():
    st.markdown(
        """
        <section class="hero-shell">
            <div class="hero-eyebrow">Secondhand Marketplace + 7-11 MyShip</div>
            <div class="hero-title">二手交易中心 x 7-11 賣貨便</div>
            <p class="hero-copy">
                商品先在本站刊登、展示與溝通，成交後再由賣家補上 7-11 賣貨便連結，
                買家可直接跳轉到官方頁面完成下單與後續出貨。
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(admin_delete_key: str):
    """Keep management and filters in the sidebar."""
    with st.sidebar:
        st.header("管理與篩選")

        if admin_delete_key:
            st.caption("管理模式可控制刪除、賣貨便連結更新與商品狀態切換。")
            with st.form("admin-login-form", clear_on_submit=False):
                admin_input = st.text_input("管理者刪除碼", type="password")
                login_clicked = st.form_submit_button("啟用管理模式", use_container_width=True)

            if login_clicked:
                if hmac.compare_digest(normalize_text(admin_input), admin_delete_key):
                    st.session_state["admin_verified"] = True
                    set_flash("管理模式已啟用。")
                    st.rerun()
                else:
                    set_flash("管理者刪除碼錯誤。", "error")
                    st.rerun()

            if st.session_state["admin_verified"]:
                st.success("目前已解鎖管理模式。")
                if st.button("關閉管理模式", use_container_width=True):
                    st.session_state["admin_verified"] = False
                    set_flash("管理模式已關閉。")
                    st.rerun()
            else:
                st.info("目前為一般瀏覽模式。")
        else:
            st.session_state["admin_verified"] = False
            st.warning("尚未設定 ADMIN_DELETE_KEY，因此管理功能已停用。")

        st.divider()
        st.subheader("搜尋條件")
        keyword = st.text_input("關鍵字", placeholder="搜尋名稱、描述、地點或賣家")
        category = st.selectbox(
            "分類",
            options=["all", "3C", "furniture", "clothing", "books", "sports", "other"],
            format_func=format_category,
        )
        status = st.selectbox(
            "狀態",
            options=["all", "available", "sold"],
            format_func=format_status,
        )

        st.divider()
        st.subheader("官方入口")
        st.link_button("前往 7-11 賣貨便首頁", MYSHIP_HOME_URL, use_container_width=True)
        st.link_button("建立賣貨便連結", MYSHIP_CREATE_URL, use_container_width=True)
        st.caption("提醒：Streamlit Community Cloud 上執行時，本地 SQLite 資料不保證永久保留。")

    return keyword, category, status


def render_stats(listings):
    total_count = len(listings)
    available_count = sum(1 for listing in listings if listing["status"] == "available")
    linked_count = sum(1 for listing in listings if listing["myship_url"])

    stat_columns = st.columns(3)
    stat_columns[0].metric("目前商品數", total_count)
    stat_columns[1].metric("可交易商品", available_count)
    stat_columns[2].metric("已綁定賣貨便", linked_count)


def render_listing_form():
    """Public listing form for quick item submission."""
    with st.container(border=True):
        st.subheader("刊登商品")
        st.caption("可先上架商品，等買家確定成交後，再補上 7-11 賣貨便連結。")

        with st.form("create-listing-form", clear_on_submit=True):
            title = st.text_input("商品名稱")
            category = st.selectbox(
                "分類",
                options=["3C", "furniture", "clothing", "books", "sports", "other"],
                format_func=format_category,
            )

            field_col_1, field_col_2 = st.columns(2)
            with field_col_1:
                price = st.number_input("售價", min_value=0, step=1)
                seller_name = st.text_input("賣家名稱")
                location = st.text_input("交易地點")
            with field_col_2:
                condition = st.selectbox(
                    "商品狀況",
                    options=["mint", "good", "fair", "cleanup"],
                    format_func=format_condition,
                )
                contact = st.text_input("聯絡方式")
                myship_url = st.text_input("7-11 賣貨便連結", placeholder="https://myship.7-11.com.tw/...")

            description = st.text_area("商品描述", height=120)
            uploaded_files = st.file_uploader(
                "商品照片",
                type=["png", "jpg", "jpeg", "webp", "gif"],
                accept_multiple_files=True,
                help="每筆商品最多 5 張照片，系統會自動縮圖與壓縮。",
            )

            if uploaded_files:
                st.image(
                    [uploaded_file.getvalue() for uploaded_file in uploaded_files[:MAX_PHOTO_COUNT]],
                    width=140,
                    caption=[f"預覽 {index + 1}" for index in range(min(len(uploaded_files), MAX_PHOTO_COUNT))],
                )

            submitted = st.form_submit_button("新增商品", use_container_width=True)

        if not submitted:
            return

        uploaded_files = uploaded_files or []

        required_fields = [
            normalize_text(title),
            normalize_text(seller_name),
            normalize_text(contact),
            normalize_text(location),
            normalize_text(description),
        ]

        if not all(required_fields):
            set_flash("請完整填寫所有必填欄位。", "error")
            st.rerun()

        if uploaded_files and len(uploaded_files) > MAX_PHOTO_COUNT:
            set_flash(f"照片最多只能上傳 {MAX_PHOTO_COUNT} 張。", "error")
            st.rerun()

        validated_myship_url, url_error = validate_myship_url(myship_url)
        if url_error:
            set_flash(url_error, "error")
            st.rerun()

        try:
            encoded_photos = [image_to_data_url(uploaded_file) for uploaded_file in uploaded_files]
        except ValueError as error:
            set_flash(str(error), "error")
            st.rerun()

        create_listing(
            {
                "title": normalize_text(title),
                "category": category,
                "price": int(price),
                "condition": condition,
                "description": normalize_text(description),
                "seller_name": normalize_text(seller_name),
                "contact": normalize_text(contact),
                "location": normalize_text(location),
                "myship_url": validated_myship_url,
                "photos": encoded_photos,
                "status": "available",
            }
        )
        set_flash("商品已成功新增。")
        st.rerun()


def render_message_thread(messages):
    if not messages:
        st.info("目前還沒有留言，歡迎先從這裡討論交易細節。")
        return

    for message in messages:
        role = message["role"]
        role_label = ROLE_LABELS.get(role, role)
        role_class = "message-item--buyer" if role == "buyer" else "message-item--seller"
        safe_author = html.escape(message["author_name"])
        safe_content = html.escape(message["content"])
        safe_time = html.escape(format_datetime(message["created_at"]))

        st.markdown(
            f"""
            <div class="message-item {role_class}">
                <div class="message-header">
                    <strong>{role_label} / {safe_author}</strong>
                    <span>{safe_time}</span>
                </div>
                <p class="message-content">{safe_content}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_listing_card(listing: dict):
    """Render one listing card with photo, logistics and message controls."""
    with st.container(border=True):
        top_columns = st.columns([1.05, 1.45], gap="large")

        with top_columns[0]:
            decoded_photos = [decode_data_url(photo) for photo in listing["photos"]]
            decoded_photos = [photo for photo in decoded_photos if photo]

            if decoded_photos:
                st.image(decoded_photos, use_container_width=True)
            else:
                st.info("尚未上傳商品照片。")

        with top_columns[1]:
            st.subheader(listing["title"])

            badge_class = (
                "market-badge market-badge--available"
                if listing["status"] == "available"
                else "market-badge market-badge--sold"
            )
            st.markdown(
                f"""
                <div class="badge-row">
                    <span class="market-badge">{html.escape(format_category(listing["category"]))}</span>
                    <span class="market-badge">{html.escape(format_condition(listing["condition"]))}</span>
                    <span class="{badge_class}">{html.escape(format_status(listing["status"]))}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                f"""
                <div class="meta-block">
                    <strong>售價：</strong> NT$ {listing["price"]:,}<br />
                    <strong>賣家：</strong> {html.escape(listing["seller_name"])}<br />
                    <strong>聯絡：</strong> {html.escape(listing["contact"])}<br />
                    <strong>地點：</strong> {html.escape(listing["location"])}<br />
                    <strong>刊登時間：</strong> {html.escape(format_datetime(listing["created_at"]))}
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.write(listing["description"])

            link_columns = st.columns([1, 1])
            if listing["myship_url"]:
                link_columns[0].link_button(
                    "前往 7-11 賣貨便下單",
                    listing["myship_url"],
                    use_container_width=True,
                )
                link_columns[1].link_button(
                    "查看官方首頁",
                    MYSHIP_HOME_URL,
                    use_container_width=True,
                )
            else:
                link_columns[0].link_button(
                    "建立賣貨便連結",
                    MYSHIP_CREATE_URL,
                    use_container_width=True,
                )
                link_columns[1].info("此商品目前尚未綁定賣貨便連結。")

        if st.session_state["admin_verified"]:
            st.caption("管理模式下可更新賣貨便連結、切換商品狀態與刪除商品。")
            with st.form(f"manage-listing-{listing['id']}", clear_on_submit=False):
                myship_value = st.text_input(
                    "更新 7-11 賣貨便連結",
                    value=listing["myship_url"] or "",
                    key=f"myship-input-{listing['id']}",
                )
                action_columns = st.columns(3)
                save_link = action_columns[0].form_submit_button("儲存賣貨便連結", use_container_width=True)
                toggle_status = action_columns[1].form_submit_button(
                    "標記已售出" if listing["status"] == "available" else "重新上架",
                    use_container_width=True,
                )
                remove_listing = action_columns[2].form_submit_button("刪除商品", use_container_width=True)

            if save_link:
                validated_url, url_error = validate_myship_url(myship_value)
                if url_error:
                    set_flash(url_error, "error")
                else:
                    update_myship_link(listing["id"], validated_url)
                    set_flash("賣貨便連結已更新。")
                st.rerun()

            if toggle_status:
                next_status = "sold" if listing["status"] == "available" else "available"
                update_listing_status(listing["id"], next_status)
                set_flash("商品狀態已更新。")
                st.rerun()

            if remove_listing:
                delete_listing(listing["id"])
                set_flash("商品已刪除。")
                st.rerun()

        with st.expander("買家與賣家留言", expanded=False):
            render_message_thread(listing["messages"])

            with st.form(f"message-form-{listing['id']}", clear_on_submit=True):
                form_columns = st.columns([0.6, 1.1])
                role = form_columns[0].selectbox(
                    "身份",
                    options=["buyer", "seller"],
                    format_func=lambda value: ROLE_LABELS[value],
                    key=f"message-role-{listing['id']}",
                )
                author_name = form_columns[1].text_input(
                    "留言者名稱",
                    key=f"message-author-{listing['id']}",
                )
                content = st.text_area(
                    "留言內容",
                    height=100,
                    key=f"message-content-{listing['id']}",
                )
                send_message = st.form_submit_button("送出留言", use_container_width=True)

            if send_message:
                normalized_author = normalize_text(author_name)
                normalized_content = normalize_text(content)

                if not normalized_author or not normalized_content:
                    set_flash("請填寫留言者名稱與留言內容。", "error")
                elif len(normalized_content) > MAX_MESSAGE_LENGTH:
                    set_flash(f"留言內容請控制在 {MAX_MESSAGE_LENGTH} 字以內。", "error")
                else:
                    add_message(listing["id"], role, normalized_author, normalized_content)
                    set_flash("留言已送出。")
                st.rerun()


def render_listing_board(listings):
    st.subheader("商品列表")
    st.caption("本站負責上架與溝通；正式下單與物流交付由 7-11 賣貨便處理。")

    if not listings:
        st.markdown(
            """
            <div class="listing-empty">
                目前沒有符合條件的商品，試著調整搜尋條件，或先刊登一筆新商品吧。
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    for listing in listings:
        render_listing_card(listing)
        st.divider()


def render_transaction_steps():
    with st.expander("此網頁交易流程步驟提示", expanded=False):
        st.markdown(
            """
            1. 賣家先在本站刊登商品，填寫描述、價格與照片。
            2. 買家透過商品頁面查看內容，並在留言區與賣家確認交易細節。
            3. 雙方確認成交後，由賣家建立 7-11 賣貨便連結並貼回商品頁面。
            4. 買家點擊賣貨便連結，跳轉到 7-11 官方頁面完成下單流程。
            5. 後續寄件、配送與取貨流程由 7-11 賣貨便處理。
            """
        )


def main():
    bootstrap_database()
    inject_custom_style()
    ensure_session_state()
    show_flash()

    admin_delete_key = get_admin_delete_key()
    keyword, category, status = render_sidebar(admin_delete_key)
    listings = list_listings(keyword=keyword, category=category, status=status)

    render_hero()
    render_stats(listings)
    render_transaction_steps()


    form_tab, listings_tab = st.tabs(["刊登商品", "商品列表"])

    with form_tab:
        render_listing_form()

    with listings_tab:
        render_listing_board(listings)


if __name__ == "__main__":
    main()
