import io
import json
from datetime import date
from pathlib import Path
from uuid import uuid4

import streamlit as st
from fpdf import FPDF


APP_TITLE = "夯到拉排程工具"
AUTOSAVE_PATH = Path("hangdaola_autosave.json")


def create_default_data() -> dict:
    return {
        "version": 1,
        "workspace_name": "我的夯到拉",
        "tabs": [
            {
                "id": str(uuid4()),
                "name": "分頁 1",
                "items": [
                    {
                        "id": str(uuid4()),
                        "title": "範例項目",
                        "content": "在這裡輸入內容...",
                        "due_date": "",
                        "tags": [],
                    }
                ],
            }
        ],
    }


def validate_data(data: dict) -> dict:
    if not isinstance(data, dict):
        return create_default_data()

    tabs = data.get("tabs")
    if not isinstance(tabs, list) or len(tabs) == 0:
        return create_default_data()

    normalized_tabs = []
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        tab_name = tab.get("name", "未命名分頁")
        items = tab.get("items", [])
        if not isinstance(items, list):
            items = []

        normalized_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized_items.append(
                {
                    "id": str(item.get("id") or uuid4()),
                    "title": str(item.get("title", "")),
                    "content": str(item.get("content", "")),
                    "due_date": str(item.get("due_date", "")),
                    "tags": [str(tag) for tag in item.get("tags", []) if str(tag).strip()],
                }
            )

        normalized_tabs.append(
            {
                "id": str(tab.get("id") or uuid4()),
                "name": str(tab_name),
                "items": normalized_items,
            }
        )

    if not normalized_tabs:
        return create_default_data()

    return {
        "version": int(data.get("version", 1)),
        "workspace_name": str(data.get("workspace_name", "我的夯到拉")),
        "tabs": normalized_tabs,
    }


def load_from_disk(path: Path) -> dict:
    if not path.exists():
        return create_default_data()

    try:
        return validate_data(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return create_default_data()


def save_to_disk(data: dict, path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def init_state() -> None:
    if "data" not in st.session_state:
        st.session_state.data = load_from_disk(AUTOSAVE_PATH)
    if "last_saved_snapshot" not in st.session_state:
        st.session_state.last_saved_snapshot = ""
    if "shared_path" not in st.session_state:
        st.session_state.shared_path = ""


def get_active_save_path() -> Path:
    shared_path = str(st.session_state.get("shared_path", "")).strip()
    return Path(shared_path) if shared_path else AUTOSAVE_PATH


def autosave_if_needed() -> None:
    snapshot = json.dumps(st.session_state.data, ensure_ascii=False, sort_keys=True)
    if snapshot != st.session_state.last_saved_snapshot:
        save_to_disk(st.session_state.data, get_active_save_path())
        st.session_state.last_saved_snapshot = snapshot


def add_tab() -> None:
    st.session_state.data["tabs"].append(
        {"id": str(uuid4()), "name": f"分頁 {len(st.session_state.data['tabs']) + 1}", "items": []}
    )


def remove_tab(index: int) -> None:
    if len(st.session_state.data["tabs"]) <= 1:
        return
    st.session_state.data["tabs"].pop(index)


def move_tab(index: int, direction: int) -> None:
    target = index + direction
    tabs = st.session_state.data["tabs"]
    if 0 <= target < len(tabs):
        tabs[index], tabs[target] = tabs[target], tabs[index]


def add_item(tab: dict) -> None:
    tab["items"].append(
        {
            "id": str(uuid4()),
            "title": "新項目",
            "content": "",
            "due_date": "",
            "tags": [],
        }
    )


def remove_item(tab: dict, item_index: int) -> None:
    tab["items"].pop(item_index)


def move_item(tab: dict, item_index: int, direction: int) -> None:
    target = item_index + direction
    if 0 <= target < len(tab["items"]):
        tab["items"][item_index], tab["items"][target] = tab["items"][target], tab["items"][item_index]


def str_to_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def create_pdf_bytes(data: dict) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", size=16)
    pdf.cell(0, 10, txt=f"HangDaoLa - {data.get('workspace_name', '')}", ln=True)
    pdf.ln(2)

    for tab in data.get("tabs", []):
        pdf.set_font("Helvetica", style="B", size=13)
        pdf.multi_cell(0, 8, txt=f"[Tab] {tab.get('name', 'Untitled')}")
        pdf.ln(1)
        for item in tab.get("items", []):
            pdf.set_font("Helvetica", style="", size=11)
            due_text = item.get("due_date", "")
            tags = ", ".join(item.get("tags", []))
            pdf.multi_cell(0, 7, txt=f"- {item.get('title', '')}")
            if due_text:
                pdf.multi_cell(0, 6, txt=f"  Due: {due_text}")
            if tags:
                pdf.multi_cell(0, 6, txt=f"  Tags: {tags}")
            content = item.get("content", "").strip()
            if content:
                pdf.multi_cell(0, 6, txt=f"  Content: {content}")
            pdf.ln(1)
        pdf.ln(1)

    return bytes(pdf.output(dest="S"))


def matches_filter(item: dict, search_query: str, selected_tags: list[str], due_before: date | None) -> bool:
    haystack = f"{item.get('title', '')}\n{item.get('content', '')}\n{' '.join(item.get('tags', []))}".lower()
    if search_query and search_query not in haystack:
        return False
    if selected_tags and not set(selected_tags).issubset(set(item.get("tags", []))):
        return False
    if due_before:
        due_date = str_to_date(item.get("due_date", ""))
        if due_date is None or due_date > due_before:
            return False
    return True


st.set_page_config(page_title=APP_TITLE, layout="wide")
init_state()

st.title(APP_TITLE)
st.caption("支援多分頁、本機暫存、多人共用檔案、搜尋/標籤、JSON/PDF 匯出。")

with st.sidebar:
    st.subheader("工作區設定")
    st.session_state.data["workspace_name"] = st.text_input(
        "工作區名稱", value=st.session_state.data.get("workspace_name", "我的夯到拉")
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("新增分頁", use_container_width=True):
            add_tab()
            st.rerun()
    with col_b:
        if st.button("手動儲存", use_container_width=True):
            save_to_disk(st.session_state.data, get_active_save_path())
            st.success("已儲存到本地檔案。")

    st.divider()
    st.subheader("多人共用（共享檔案）")
    st.session_state.shared_path = st.text_input(
        "共享 JSON 路徑（可留空）",
        value=st.session_state.shared_path,
        placeholder="例如：D:/shared/hangdaola-team.json",
    )
    col_sync_a, col_sync_b = st.columns(2)
    with col_sync_a:
        if st.button("載入共享檔", use_container_width=True):
            shared = str(st.session_state.shared_path).strip()
            if not shared:
                st.warning("請先輸入共享檔路徑。")
            else:
                loaded = load_from_disk(Path(shared))
                st.session_state.data = loaded
                save_to_disk(st.session_state.data, Path(shared))
                st.success("已載入共享檔。")
                st.rerun()
    with col_sync_b:
        if st.button("同步到共享檔", use_container_width=True):
            shared = str(st.session_state.shared_path).strip()
            if not shared:
                st.warning("請先輸入共享檔路徑。")
            else:
                save_to_disk(st.session_state.data, Path(shared))
                st.success("已同步到共享檔。")

    st.divider()
    st.subheader("資料匯出 / 匯入")

    export_payload = json.dumps(st.session_state.data, ensure_ascii=False, indent=2)
    st.download_button(
        "Export JSON",
        data=export_payload.encode("utf-8"),
        file_name=f"{st.session_state.data['workspace_name']}.json",
        mime="application/json",
        use_container_width=True,
    )
    st.download_button(
        "Export PDF",
        data=create_pdf_bytes(st.session_state.data),
        file_name=f"{st.session_state.data['workspace_name']}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

    uploaded = st.file_uploader("Import JSON", type=["json"])
    if uploaded is not None:
        try:
            imported = validate_data(json.load(uploaded))
            st.session_state.data = imported
            save_to_disk(st.session_state.data, AUTOSAVE_PATH)
            st.success("匯入成功，已還原你的夯到拉列表。")
            st.rerun()
        except Exception:
            st.error("匯入失敗：請確認檔案格式是否正確。")

all_tags = sorted(
    {tag for tab in st.session_state.data["tabs"] for item in tab["items"] for tag in item.get("tags", [])}
)
filter_col_a, filter_col_b, filter_col_c = st.columns([2, 2, 2])
with filter_col_a:
    search_keyword = st.text_input("全域搜尋", placeholder="標題 / 內容 / 標籤")
with filter_col_b:
    selected_tags = st.multiselect("標籤篩選（需全部符合）", options=all_tags)
with filter_col_c:
    due_before = st.date_input("到期日（含）", value=None, format="YYYY-MM-DD")

tabs = st.session_state.data["tabs"]
streamlit_tabs = st.tabs([tab["name"] for tab in tabs])

for idx, (tab_ui, tab_data) in enumerate(zip(streamlit_tabs, tabs)):
    with tab_ui:
        header_col, order_col, delete_col = st.columns([3, 2, 1])
        with header_col:
            tab_data["name"] = st.text_input(
                "分頁名稱",
                value=tab_data["name"],
                key=f"tab_name_{tab_data['id']}",
            )
        with order_col:
            up_col, down_col = st.columns(2)
            with up_col:
                if st.button("分頁上移", key=f"tab_up_{tab_data['id']}", use_container_width=True):
                    move_tab(idx, -1)
                    st.rerun()
            with down_col:
                if st.button("分頁下移", key=f"tab_down_{tab_data['id']}", use_container_width=True):
                    move_tab(idx, 1)
                    st.rerun()
        with delete_col:
            st.write("")
            st.write("")
            if st.button("刪除分頁", key=f"delete_tab_{tab_data['id']}"):
                remove_tab(idx)
                st.rerun()

        st.write(f"### {tab_data['name']} - 項目列表")
        if st.button("新增項目", key=f"add_item_{tab_data['id']}"):
            add_item(tab_data)
            st.rerun()

        if not tab_data["items"]:
            st.info("這個分頁還沒有項目，先新增一筆吧。")

        has_any_match = False
        for item_index, item in enumerate(tab_data["items"]):
            if not matches_filter(item, search_keyword.lower().strip(), selected_tags, due_before):
                continue
            has_any_match = True
            st.markdown("---")
            row_a, row_b, row_c = st.columns([3, 2, 1])
            with row_a:
                tab_data["items"][item_index]["title"] = st.text_input(
                    f"標題 {item_index + 1}",
                    value=item["title"],
                    key=f"title_{tab_data['id']}_{item['id']}",
                )
            with row_b:
                up_col, down_col = st.columns(2)
                with up_col:
                    if st.button("上移", key=f"item_up_{tab_data['id']}_{item['id']}", use_container_width=True):
                        move_item(tab_data, item_index, -1)
                        st.rerun()
                with down_col:
                    if st.button("下移", key=f"item_down_{tab_data['id']}_{item['id']}", use_container_width=True):
                        move_item(tab_data, item_index, 1)
                        st.rerun()
            with row_c:
                if st.button("刪除", key=f"del_item_{tab_data['id']}_{item['id']}", use_container_width=True):
                    remove_item(tab_data, item_index)
                    st.rerun()

            date_col, tag_col = st.columns([1, 2])
            with date_col:
                parsed_due = str_to_date(item.get("due_date", ""))
                chosen_date = st.date_input(
                    f"到期日 {item_index + 1}",
                    value=parsed_due,
                    key=f"due_{tab_data['id']}_{item['id']}",
                    format="YYYY-MM-DD",
                )
                tab_data["items"][item_index]["due_date"] = (
                    chosen_date.isoformat() if chosen_date else ""
                )
            with tag_col:
                tags_raw = st.text_input(
                    f"標籤 {item_index + 1}（用逗號分隔）",
                    value=",".join(item.get("tags", [])),
                    key=f"tags_{tab_data['id']}_{item['id']}",
                )
                tab_data["items"][item_index]["tags"] = [
                    tag.strip() for tag in tags_raw.split(",") if tag.strip()
                ]

            tab_data["items"][item_index]["content"] = st.text_area(
                f"內容 {item_index + 1}",
                value=item["content"],
                key=f"content_{tab_data['id']}_{item['id']}",
                height=160,
            )
        if tab_data["items"] and not has_any_match:
            st.info("這個分頁沒有符合篩選條件的項目。")

autosave_if_needed()
st.caption(f"目前自動儲存檔：`{get_active_save_path().resolve()}`")
