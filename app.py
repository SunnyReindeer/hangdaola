import base64
import io
import json
from pathlib import Path
from uuid import uuid4

import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps
try:
    from streamlit_sortables import sort_items
except Exception:
    sort_items = None


APP_TITLE = "夯到拉 Tier List"
AUTOSAVE_PATH = Path("hangdaola_autosave.json")
TIER_DEFAULTS = ["夯", "頂級", "人上人", "NPC", "拉"]
CARD_SIZE = (140, 140)
COMPRESS_LONG_EDGE_DEFAULT = 1280
COMPRESS_JPEG_QUALITY_DEFAULT = 78


def create_default_board(name: str = "我的榜單") -> dict:
    return {
        "id": str(uuid4()),
        "name": name,
        "title": "我的夯到拉排行榜",
        "tiers": TIER_DEFAULTS.copy(),
        "items": [],
        "placements": {},
    }


def create_default_data() -> dict:
    return {"version": 2, "workspace_name": "我的夯到拉", "boards": [create_default_board("分頁 1")]}


def migrate_legacy_data(data: dict) -> dict:
    if not isinstance(data, dict):
        return create_default_data()
    if "boards" in data:
        return data

    # Backward compatibility for old schema: workspace_name + tabs/items.
    tabs = data.get("tabs", [])
    if not isinstance(tabs, list) or not tabs:
        return create_default_data()

    boards = []
    for i, tab in enumerate(tabs):
        if not isinstance(tab, dict):
            continue
        board = create_default_board(str(tab.get("name", f"分頁 {i + 1}")))
        board["title"] = f"{board['name']} 排行榜"

        converted_items = []
        placements: dict[str, list[str]] = {tier: [] for tier in board["tiers"]}
        for old_item in tab.get("items", []):
            if not isinstance(old_item, dict):
                continue
            # Legacy data may not have image. Create text placeholder card for compatibility.
            placeholder = Image.new("RGB", CARD_SIZE, color=(250, 250, 250))
            draw = ImageDraw.Draw(placeholder)
            draw.text((10, 60), safe_text(old_item.get("title", "項目"))[:10], fill=(50, 50, 50), font=pick_font(16))
            buf = io.BytesIO()
            placeholder.save(buf, format="PNG")
            item_id = str(old_item.get("id") or uuid4())
            converted_items.append(
                {
                    "id": item_id,
                    "name": str(old_item.get("title", "未命名項目")),
                    "mime": "image/png",
                    "image_b64": base64.b64encode(buf.getvalue()).decode("utf-8"),
                }
            )
            # Put migrated legacy items into the middle tier by default.
            default_tier = board["tiers"][2] if len(board["tiers"]) >= 3 else board["tiers"][0]
            placements.setdefault(default_tier, []).append(item_id)

        board["items"] = converted_items
        board["placements"] = placements
        boards.append(board)

    if not boards:
        return create_default_data()

    return {
        "version": 2,
        "workspace_name": str(data.get("workspace_name", "我的夯到拉")),
        "boards": boards,
    }


def validate_data(data: dict) -> dict:
    data = migrate_legacy_data(data)
    if not isinstance(data, dict):
        return create_default_data()

    boards = data.get("boards")
    if not isinstance(boards, list) or not boards:
        return create_default_data()

    normalized_boards = []
    for board in boards:
        if not isinstance(board, dict):
            continue
        tiers = [str(t).strip() for t in board.get("tiers", []) if str(t).strip()]
        if not tiers:
            tiers = TIER_DEFAULTS.copy()
        items = []
        for item in board.get("items", []):
            if not isinstance(item, dict):
                continue
            image_b64 = str(item.get("image_b64", ""))
            if not image_b64:
                continue
            items.append(
                {
                    "id": str(item.get("id") or uuid4()),
                    "name": str(item.get("name", "未命名圖片")),
                    "image_b64": image_b64,
                    "mime": str(item.get("mime", "image/png")),
                }
            )
        placements = {}
        item_ids = {i["id"] for i in items}
        raw_placements = board.get("placements", {})
        if isinstance(raw_placements, dict):
            for tier_name, ids in raw_placements.items():
                tier_key = str(tier_name)
                if tier_key in tiers and isinstance(ids, list):
                    placements[tier_key] = [str(i) for i in ids if str(i) in item_ids]

        normalized_boards.append(
            {
                "id": str(board.get("id") or uuid4()),
                "name": str(board.get("name", "未命名分頁")),
                "title": str(board.get("title", "我的夯到拉排行榜")),
                "tiers": tiers,
                "items": items,
                "placements": placements,
            }
        )

    if not normalized_boards:
        return create_default_data()

    return {
        "version": int(data.get("version", 2)),
        "workspace_name": str(data.get("workspace_name", "我的夯到拉")),
        "boards": normalized_boards,
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
    st.session_state.data = validate_data(st.session_state.data)
    if "last_saved_snapshot" not in st.session_state:
        st.session_state.last_saved_snapshot = ""
    if "shared_path" not in st.session_state:
        st.session_state.shared_path = ""
    if "board_index" not in st.session_state:
        st.session_state.board_index = 0


def get_active_save_path() -> Path:
    shared_path = str(st.session_state.get("shared_path", "")).strip()
    return Path(shared_path) if shared_path else AUTOSAVE_PATH


def autosave_if_needed() -> None:
    snapshot = json.dumps(st.session_state.data, ensure_ascii=False, sort_keys=True)
    if snapshot != st.session_state.last_saved_snapshot:
        save_to_disk(st.session_state.data, get_active_save_path())
        st.session_state.last_saved_snapshot = snapshot


def active_board() -> dict:
    boards = st.session_state.data["boards"]
    idx = min(max(int(st.session_state.board_index), 0), len(boards) - 1)
    st.session_state.board_index = idx
    return boards[idx]


def add_board() -> None:
    boards = st.session_state.data["boards"]
    boards.append(create_default_board(f"分頁 {len(boards) + 1}"))
    st.session_state.board_index = len(boards) - 1


def remove_board(idx: int) -> None:
    boards = st.session_state.data["boards"]
    if len(boards) <= 1:
        return
    boards.pop(idx)
    st.session_state.board_index = max(0, idx - 1)


def move_board(idx: int, direction: int) -> None:
    target = idx + direction
    boards = st.session_state.data["boards"]
    if 0 <= target < len(boards):
        boards[idx], boards[target] = boards[target], boards[idx]
        st.session_state.board_index = target


def item_map(board: dict) -> dict[str, dict]:
    return {item["id"]: item for item in board["items"]}


def item_tier(board: dict, item_id: str) -> str | None:
    for tier, ids in board["placements"].items():
        if item_id in ids:
            return tier
    return None


def assign_item_to_tier(board: dict, item_id: str, tier_name: str | None) -> None:
    for ids in board["placements"].values():
        if item_id in ids:
            ids.remove(item_id)
    if tier_name:
        board["placements"].setdefault(tier_name, [])
        board["placements"][tier_name].append(item_id)


def delete_item(board: dict, item_id: str) -> None:
    board["items"] = [item for item in board["items"] if item["id"] != item_id]
    for ids in board["placements"].values():
        if item_id in ids:
            ids.remove(item_id)


def move_within_tier(board: dict, tier_name: str, item_id: str, direction: int) -> None:
    ids = board["placements"].get(tier_name, [])
    if item_id not in ids:
        return
    idx = ids.index(item_id)
    target = idx + direction
    if 0 <= target < len(ids):
        ids[idx], ids[target] = ids[target], ids[idx]


def compact_and_validate_placements(board: dict) -> None:
    valid_ids = {item["id"] for item in board["items"]}
    for tier in board["tiers"]:
        current = board["placements"].get(tier, [])
        board["placements"][tier] = [item_id for item_id in current if item_id in valid_ids]


def apply_drag_result(board: dict, dragged: list[dict]) -> None:
    # dragged format from streamlit-sortables:
    # [{"header":"圖片池","items":[...label...]}, {"header":"夯","items":[...]} ...]
    label_to_id = {f"{item['name']} ({item['id'][:6]})": item["id"] for item in board["items"]}
    assigned: set[str] = set()
    new_placements: dict[str, list[str]] = {tier: [] for tier in board["tiers"]}

    for box in dragged:
        header = str(box.get("header", ""))
        labels = box.get("items", [])
        if not isinstance(labels, list):
            continue
        for label in labels:
            item_id = label_to_id.get(str(label))
            if not item_id or item_id in assigned:
                continue
            assigned.add(item_id)
            if header in new_placements:
                new_placements[header].append(item_id)

    board["placements"] = new_placements


def image_bytes_from_item(item: dict) -> bytes:
    return base64.b64decode(item["image_b64"])


def compress_upload_image(
    raw_bytes: bytes,
    max_long_edge: int = COMPRESS_LONG_EDGE_DEFAULT,
    jpeg_quality: int = COMPRESS_JPEG_QUALITY_DEFAULT,
) -> tuple[bytes, str]:
    image = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    image.thumbnail((max_long_edge, max_long_edge), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=jpeg_quality, optimize=True)
    return out.getvalue(), "image/jpeg"


def build_fitted_card(item: dict, card_size: tuple[int, int] = CARD_SIZE) -> Image.Image:
    """
    Keep original aspect ratio for both landscape and portrait images,
    then center the image on a fixed-size card background.
    """
    source = Image.open(io.BytesIO(image_bytes_from_item(item))).convert("RGB")
    fitted = ImageOps.contain(source, card_size, method=Image.Resampling.LANCZOS)
    card = Image.new("RGB", card_size, color=(248, 249, 250))
    offset_x = (card_size[0] - fitted.width) // 2
    offset_y = (card_size[1] - fitted.height) // 2
    card.paste(fitted, (offset_x, offset_y))
    return card


def card_preview_bytes(item: dict, card_size: tuple[int, int] = CARD_SIZE) -> bytes:
    card = build_fitted_card(item, card_size=card_size)
    out = io.BytesIO()
    card.save(out, format="PNG")
    return out.getvalue()


def safe_text(value: str) -> str:
    return str(value or "").strip()


def pick_font(size: int = 18) -> ImageFont.ImageFont:
    font_candidates = [
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in font_candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_board_png(board: dict) -> bytes:
    label_w = 160
    gap = 10
    row_h = CARD_SIZE[1] + 24
    tiers = board["tiers"]
    placements = board["placements"]
    max_items = max([len(placements.get(t, [])) for t in tiers] + [1])
    canvas_w = label_w + gap + (CARD_SIZE[0] + gap) * max_items + 20
    canvas_h = 90 + (row_h + gap) * len(tiers) + 30

    canvas = Image.new("RGB", (canvas_w, canvas_h), color=(245, 247, 250))
    draw = ImageDraw.Draw(canvas)
    title_font = pick_font(30)
    label_font = pick_font(22)
    small_font = pick_font(16)
    draw.text((18, 16), safe_text(board["title"]), fill=(33, 37, 41), font=title_font)

    items_by_id = item_map(board)
    y = 74
    tier_colors = [(255, 97, 97), (255, 153, 51), (255, 211, 77), (143, 212, 98), (126, 174, 255)]

    for i, tier in enumerate(tiers):
        color = tier_colors[i % len(tier_colors)]
        draw.rounded_rectangle((10, y, label_w - 5, y + row_h), radius=10, fill=color)
        draw.text((20, y + 12), safe_text(tier), fill=(20, 20, 20), font=label_font)
        draw.rounded_rectangle((label_w, y, canvas_w - 12, y + row_h), radius=10, fill=(255, 255, 255))

        x = label_w + 8
        for item_id in placements.get(tier, []):
            item = items_by_id.get(item_id)
            if not item:
                continue
            try:
                tile = build_fitted_card(item, card_size=CARD_SIZE)
                canvas.paste(tile, (x, y + 10))
                draw.rectangle((x, y + 10, x + CARD_SIZE[0], y + 10 + CARD_SIZE[1]), outline=(200, 200, 200))
                draw.text((x + 4, y + CARD_SIZE[1] - 4), safe_text(item["name"])[:12], fill=(50, 50, 50), font=small_font)
                x += CARD_SIZE[0] + gap
            except Exception:
                continue
        y += row_h + gap

    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


st.set_page_config(page_title=APP_TITLE, layout="wide")
init_state()

st.title(APP_TITLE)
st.caption("參考層級排行榜互動：分頁管理、圖片池、分配到層級、JSON/PNG 匯出。")

with st.sidebar:
    st.subheader("工作區")
    st.session_state.data["workspace_name"] = st.text_input(
        "工作區名稱",
        value=st.session_state.data.get("workspace_name", "我的夯到拉"),
    )
    board_names = [b.get("name", "未命名分頁") for b in st.session_state.data["boards"]]
    st.session_state.board_index = st.selectbox(
        "目前分頁",
        options=list(range(len(board_names))),
        format_func=lambda i: board_names[i],
        index=min(st.session_state.board_index, len(board_names) - 1),
    )
    b = active_board()
    b["name"] = st.text_input("分頁名稱", value=b["name"])

    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1:
        if st.button("新增分頁", use_container_width=True):
            add_board()
            st.rerun()
    with col_b2:
        if st.button("上移", use_container_width=True):
            move_board(st.session_state.board_index, -1)
            st.rerun()
    with col_b3:
        if st.button("下移", use_container_width=True):
            move_board(st.session_state.board_index, 1)
            st.rerun()

    if st.button("刪除目前分頁", use_container_width=True):
        remove_board(st.session_state.board_index)
        st.rerun()

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
            shared = safe_text(st.session_state.shared_path)
            if shared:
                st.session_state.data = load_from_disk(Path(shared))
                save_to_disk(st.session_state.data, Path(shared))
                st.success("已載入共享檔")
                st.rerun()
            st.warning("請先輸入共享檔路徑")
    with col_sync_b:
        if st.button("同步到共享檔", use_container_width=True):
            shared = safe_text(st.session_state.shared_path)
            if shared:
                save_to_disk(st.session_state.data, Path(shared))
                st.success("已同步到共享檔")
            else:
                st.warning("請先輸入共享檔路徑")

    st.divider()
    st.subheader("效能設定")
    st.session_state.upload_accelerate = st.checkbox(
        "加速模式（上傳時壓縮）",
        value=st.session_state.get("upload_accelerate", True),
        help="壓縮後可明顯降低檔案大小，提升載入和拖放速度。",
    )
    st.session_state.compress_long_edge = st.slider(
        "最大邊長（像素）",
        min_value=640,
        max_value=2048,
        value=st.session_state.get("compress_long_edge", COMPRESS_LONG_EDGE_DEFAULT),
        step=64,
    )
    st.session_state.compress_quality = st.slider(
        "壓縮品質（JPEG）",
        min_value=50,
        max_value=95,
        value=st.session_state.get("compress_quality", COMPRESS_JPEG_QUALITY_DEFAULT),
        step=1,
    )

    st.divider()
    st.subheader("匯入 / 匯出")
    export_payload = json.dumps(st.session_state.data, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button(
        "Export JSON",
        data=export_payload,
        file_name=f"{st.session_state.data['workspace_name']}.json",
        mime="application/json",
        use_container_width=True,
    )
    st.download_button(
        "Export PNG 榜單圖",
        data=render_board_png(active_board()),
        file_name=f"{active_board()['name']}.png",
        mime="image/png",
        use_container_width=True,
    )
    uploaded = st.file_uploader("Import JSON", type=["json"])
    if uploaded is not None:
        try:
            st.session_state.data = validate_data(json.load(uploaded))
            st.success("匯入成功")
            st.rerun()
        except Exception:
            st.error("匯入失敗：請確認 JSON 格式")

board = active_board()
compact_and_validate_placements(board)
board["title"] = st.text_input("榜單標題", value=board["title"])
tier_lines = st.text_area("層級設定（每行一個層級）", value="\n".join(board["tiers"]), height=130)
new_tiers = [line.strip() for line in tier_lines.splitlines() if line.strip()]
if new_tiers:
    old_tiers = board["tiers"]
    board["tiers"] = new_tiers
    for tier in old_tiers:
        if tier not in new_tiers:
            for item_id in board["placements"].get(tier, []):
                assign_item_to_tier(board, item_id, None)
            board["placements"].pop(tier, None)
    for tier in new_tiers:
        board["placements"].setdefault(tier, [])

st.subheader("圖片池")
uploaded_images = st.file_uploader(
    "新增圖片（可多選）",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)
if uploaded_images:
    existing_names = {item["name"] for item in board["items"]}
    added_count = 0
    skipped_count = 0
    for file in uploaded_images:
        if file.name in existing_names:
            skipped_count += 1
            continue
        original = file.getvalue()
        if st.session_state.get("upload_accelerate", True):
            compressed, mime = compress_upload_image(
                original,
                max_long_edge=int(st.session_state.get("compress_long_edge", COMPRESS_LONG_EDGE_DEFAULT)),
                jpeg_quality=int(st.session_state.get("compress_quality", COMPRESS_JPEG_QUALITY_DEFAULT)),
            )
            store_bytes = compressed
            store_mime = mime
        else:
            store_bytes = original
            store_mime = file.type or "image/png"

        board["items"].append(
            {
                "id": str(uuid4()),
                "name": file.name,
                "mime": store_mime,
                "image_b64": base64.b64encode(store_bytes).decode("utf-8"),
            }
        )
        added_count += 1
    st.success(f"已新增 {added_count} 張圖片，略過重複 {skipped_count} 張。")

search = st.text_input("搜尋圖片名稱", placeholder="輸入關鍵字")
items = board["items"]
items_by_id = item_map(board)
filtered_items = [i for i in items if search.lower().strip() in i["name"].lower()]

selected_delete_ids = st.multiselect(
    "多選刪除圖片",
    options=[item["id"] for item in filtered_items],
    format_func=lambda item_id: items_by_id[item_id]["name"] if item_id in items_by_id else item_id,
)
if st.button("刪除勾選圖片", type="primary", use_container_width=False):
    if selected_delete_ids:
        for item_id in selected_delete_ids:
            delete_item(board, item_id)
        st.success(f"已刪除 {len(selected_delete_ids)} 張圖片。")
        st.rerun()
    else:
        st.info("請先勾選要刪除的圖片。")

if not items:
    st.info("目前沒有符合條件的圖片")
else:
    cols = st.columns(4)
    for idx, item in enumerate(filtered_items):
        with cols[idx % 4]:
            st.image(card_preview_bytes(item), caption=item["name"], use_container_width=True)
            if st.button("刪除圖片", key=f"del_{item['id']}", use_container_width=True):
                delete_item(board, item["id"])
                st.rerun()

st.subheader("層級榜單")
if sort_items is None:
    st.warning("未安裝拖放套件：請先 pip install streamlit-sortables")
else:
    label_of = lambda i: f"{i['name']} ({i['id'][:6]})"
    placed_ids = {item_id for tier in board["tiers"] for item_id in board["placements"].get(tier, [])}
    pool_labels = [label_of(i) for i in board["items"] if i["id"] not in placed_ids]
    drag_groups = [{"header": "圖片池", "items": pool_labels}] + [
        {
            "header": tier,
            "items": [label_of(items_by_id[item_id]) for item_id in board["placements"].get(tier, []) if item_id in items_by_id],
        }
        for tier in board["tiers"]
    ]
    dragged = sort_items(drag_groups, multi_containers=True, direction="horizontal")
    if dragged:
        apply_drag_result(board, dragged)

    st.caption("可直接拖放：圖片池 <-> 各層級，層內也可拖曳排序。")
    for tier in board["tiers"]:
        tier_ids = board["placements"].get(tier, [])
        st.markdown(f"### {tier}（{len(tier_ids)}）")
        if not tier_ids:
            st.caption("目前沒有圖片")
            continue
        cols = st.columns(5)
        for idx, item_id in enumerate(tier_ids):
            item = items_by_id.get(item_id)
            if not item:
                continue
            with cols[idx % 5]:
                st.image(card_preview_bytes(item), caption=item["name"], use_container_width=True)

autosave_if_needed()
st.caption(f"目前自動儲存檔：`{get_active_save_path().resolve()}`")
