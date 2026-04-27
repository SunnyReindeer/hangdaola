import copy
import json
from pathlib import Path
from uuid import uuid4

import streamlit as st


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
                    {"id": str(uuid4()), "title": "範例項目", "content": "在這裡輸入內容..."}
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


def autosave_if_needed() -> None:
    snapshot = json.dumps(st.session_state.data, ensure_ascii=False, sort_keys=True)
    if snapshot != st.session_state.last_saved_snapshot:
        save_to_disk(st.session_state.data, AUTOSAVE_PATH)
        st.session_state.last_saved_snapshot = snapshot


def add_tab() -> None:
    st.session_state.data["tabs"].append(
        {"id": str(uuid4()), "name": f"分頁 {len(st.session_state.data['tabs']) + 1}", "items": []}
    )


def remove_tab(index: int) -> None:
    if len(st.session_state.data["tabs"]) <= 1:
        return
    st.session_state.data["tabs"].pop(index)


def add_item(tab: dict) -> None:
    tab["items"].append({"id": str(uuid4()), "title": "新項目", "content": ""})


def remove_item(tab: dict, item_index: int) -> None:
    tab["items"].pop(item_index)


st.set_page_config(page_title=APP_TITLE, layout="wide")
init_state()

st.title(APP_TITLE)
st.caption("支援多分頁、本機暫存、Export / Import 還原資料。")

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
            save_to_disk(st.session_state.data, AUTOSAVE_PATH)
            st.success("已儲存到本地檔案。")

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

tabs = st.session_state.data["tabs"]
streamlit_tabs = st.tabs([tab["name"] for tab in tabs])

for idx, (tab_ui, tab_data) in enumerate(zip(streamlit_tabs, tabs)):
    with tab_ui:
        header_col, delete_col = st.columns([4, 1])
        with header_col:
            tab_data["name"] = st.text_input(
                "分頁名稱",
                value=tab_data["name"],
                key=f"tab_name_{tab_data['id']}",
            )
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

        for item_index, item in enumerate(copy.deepcopy(tab_data["items"])):
            st.markdown("---")
            row_a, row_b = st.columns([4, 1])
            with row_a:
                tab_data["items"][item_index]["title"] = st.text_input(
                    f"標題 {item_index + 1}",
                    value=item["title"],
                    key=f"title_{tab_data['id']}_{item['id']}",
                )
            with row_b:
                st.write("")
                st.write("")
                if st.button("刪除", key=f"del_item_{tab_data['id']}_{item['id']}"):
                    remove_item(tab_data, item_index)
                    st.rerun()

            tab_data["items"][item_index]["content"] = st.text_area(
                f"內容 {item_index + 1}",
                value=item["content"],
                key=f"content_{tab_data['id']}_{item['id']}",
                height=160,
            )

autosave_if_needed()
st.caption(f"本地暫存檔：`{AUTOSAVE_PATH.resolve()}`")
