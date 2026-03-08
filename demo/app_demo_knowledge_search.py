import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

st.set_page_config(page_title="業務ナレッジ検索デモ", layout="wide")


# ------------------------------
# session state
# ------------------------------
if "hits" not in st.session_state:
    st.session_state.hits = []

if "last_query" not in st.session_state:
    st.session_state.last_query = ""

if "jump" not in st.session_state:
    st.session_state.jump = None


# ------------------------------
# data loading
# ------------------------------
@st.cache_data
def load_docs_from_dir(json_dir: str) -> list[dict[str, Any]]:
    base = Path(json_dir)

    if not base.exists():
        raise FileNotFoundError(f"not found: {base}")

    files = sorted(base.glob("*.json"))

    if not files:
        raise FileNotFoundError(f"*.json not found in: {base}")

    docs: list[dict[str, Any]] = []

    for p in files:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            continue

        data["_source_file"] = p.name
        docs.append(data)

    return docs


# ------------------------------
# utils
# ------------------------------
def ts_to_text(ts: Any) -> str:
    if ts is None:
        return "-"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def role_label(role: str) -> str:
    return {
        "doc": "文書",
        "summary": "要約",
        "content": "本文",
    }.get(role, role)


# ------------------------------
# message extraction
# 1 document -> pseudo messages
# ------------------------------
def extract_messages(doc: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    summary = doc.get("summary", "")
    content = doc.get("content", "")
    date_value = doc.get("date")

    if summary:
        messages.append({
            "role": "summary",
            "text": summary,
            "create_time": date_value,
        })

    if content:
        messages.append({
            "role": "content",
            "text": content,
            "create_time": date_value,
        })

    return messages


# ------------------------------
# search utils
# ------------------------------
def compile_patterns(query: str, case_sensitive: bool) -> list[re.Pattern]:
    flags = 0 if case_sensitive else re.IGNORECASE
    terms = [t for t in query.split() if t]
    return [re.compile(re.escape(t), flags) for t in terms]


def find_hit_messages(messages: list[dict[str, Any]], pats: list[re.Pattern]) -> list[dict[str, Any]]:
    hit_messages = []

    for i, m in enumerate(messages):
        text = m["text"]

        if any(p.search(text) for p in pats):
            hit_count = sum(len(p.findall(text)) for p in pats)

            hit_messages.append({
                "index": i,
                "role": m["role"],
                "text": text,
                "time": m["create_time"],
                "hit_count": hit_count,
            })

    hit_messages.sort(key=lambda x: x["hit_count"], reverse=True)
    return hit_messages


def highlight_text_html(text: str, pats: list[re.Pattern]) -> str:
    escaped = html.escape(text)

    for p in pats:
        pattern = re.compile(p.pattern, p.flags)
        escaped = pattern.sub(
            lambda m: (
                '<mark style="background-color: #ffeb3b; '
                'padding: 0 2px; border-radius: 2px;">'
                f'{m.group(0)}'
                '</mark>'
            ),
            escaped,
        )

    return escaped.replace("\n", "<br>")


def is_hit_text(text: str, pats: list[re.Pattern]) -> bool:
    return any(p.search(text) for p in pats)


# ------------------------------
# search execution
# ------------------------------
def search_docs(
    data: list[dict[str, Any]],
    pats: list[re.Pattern],
    selected_category: str,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    for doc in data:
        title = doc.get("title") or ""
        summary = doc.get("summary") or ""
        content = doc.get("content") or ""
        category = doc.get("category") or "-"
        tags = doc.get("tags") or []
        tag_text = " ".join(tags) if isinstance(tags, list) else str(tags)

        if selected_category != "all" and category != selected_category:
            continue

        messages = extract_messages(doc)
        full_text = "\n\n".join(
            [title, summary, content, tag_text]
        )

        title_hit = any(p.search(title) for p in pats)
        body_hit = any(p.search(full_text) for p in pats)

        if not title_hit and not body_hit:
            continue

        hit_messages = find_hit_messages(messages, pats)

        hits.append({
            "id": doc.get("id", ""),
            "title": title,
            "category": category,
            "summary": summary,
            "content": content,
            "date": doc.get("date", ""),
            "tags": tags,
            "public_note": doc.get("public_note", ""),
            "messages": messages,
            "hit_messages": hit_messages,
            "source_file": doc.get("_source_file"),
            "title_hit": title_hit,
            "body_hit": body_hit,
        })

    hits.sort(
        key=lambda x: (
            1 if x["title_hit"] else 0,
            len(x["hit_messages"]),
            len(x["content"]),
        ),
        reverse=True,
    )
    return hits


# ------------------------------
# UI
# ------------------------------
st.title("業務ナレッジ検索デモ")
st.caption("公開用サンプルデータを対象にした検索デモです。会議メモ、FAQ、要件メモ、手順書などを横断検索できます。")
st.info("実データ・個人情報・顧客情報は含みません。公開用サンプルデータのみを使用しています。")

with st.sidebar:
    json_dir = st.text_input(
        "JSONフォルダ",
        value="demo_data"
    )

    case_sensitive = st.checkbox("大文字小文字を区別", value=False)

    try:
        preview_docs = load_docs_from_dir(json_dir)
        categories = sorted({d.get("category", "-") for d in preview_docs})
    except Exception:
        categories = []

    selected_category = st.selectbox(
        "カテゴリ",
        ["all"] + categories,
        index=0
    )

    col1, col2 = st.columns(2)
    with col1:
        search_clicked = st.button("検索", type="primary", use_container_width=True)
    with col2:
        clear_clicked = st.button("クリア", use_container_width=True)

if clear_clicked:
    st.cache_data.clear()
    st.session_state.hits = []
    st.session_state.last_query = ""
    st.session_state.jump = None
    st.toast("検索結果をクリアしました。", icon="🧹")

query = st.text_input("検索クエリ（スペース区切り）", value=st.session_state.last_query)

if search_clicked:
    if not query.strip():
        st.warning("検索クエリを入力してください。")
    else:
        try:
            data = load_docs_from_dir(json_dir)
            pats = compile_patterns(query, case_sensitive)
            hits = search_docs(data, pats, selected_category)

            st.session_state.hits = hits
            st.session_state.last_query = query
            st.session_state.jump = None

        except Exception as e:
            st.error(f"読み込みまたは検索に失敗しました: {e}")

# ------------------------------
# result view
# ------------------------------
hits = st.session_state.hits
display_query = st.session_state.last_query.strip()

if hits and display_query:
    pats = compile_patterns(display_query, case_sensitive)
    st.success(f"{len(hits)}件ヒット / クエリ: {display_query}")

    for i, h in enumerate(hits):
        title = h["title"] or "(no title)"
        expander_label = f"{i+1}. {title} [{h['category']}]"

        with st.expander(expander_label, expanded=False):
            st.caption(
                f"title_hit={h['title_hit']} / body_hit={h['body_hit']} / file={h['source_file']}"
            )

            c1, c2 = st.columns([2, 5])
            with c1:
                st.markdown("**カテゴリ**")
                st.write(h["category"])
                st.markdown("**日付**")
                st.write(h["date"] or "-")
            with c2:
                st.markdown("**タグ**")
                if h["tags"]:
                    st.write(", ".join(h["tags"]))
                else:
                    st.write("-")
                st.markdown("**要約**")
                st.write(h["summary"] or "-")

            if h["public_note"]:
                st.caption(h["public_note"])

            st.markdown("### HITした箇所")

            if not h["hit_messages"]:
                st.info("タイトルのみヒット、または要約・本文単位のヒットを抽出できませんでした。")
            else:
                for hm in h["hit_messages"][:10]:
                    col_left, col_right = st.columns([6, 1])

                    with col_left:
                        st.markdown(
                            f"**#{hm['index']+1} {role_label(hm['role'])} hits={hm['hit_count']}**"
                        )
                        st.markdown(
                            f'<div style="white-space: pre-wrap;">'
                            f'{highlight_text_html(hm["text"][:500], pats)}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        st.caption(str(hm["time"]))

                    with col_right:
                        if st.button("移動", key=f"jump_{i}_{hm['index']}"):
                            st.session_state.jump = (i, hm["index"])
                            st.rerun()

                    st.divider()

            st.markdown("### 文書詳細")

            jump = st.session_state.jump

            if jump and jump[0] == i:
                jump_idx = jump[1]
                start = max(0, jump_idx - 1)
                end = min(len(h["messages"]), jump_idx + 2)
                display_messages = list(enumerate(h["messages"][start:end], start=start))
                st.caption(f"ジャンプ先 #{jump_idx + 1} 周辺を表示中")
            else:
                display_messages = list(enumerate(h["messages"]))

            for j, msg in display_messages:
                role = role_label(msg["role"])
                text_html = highlight_text_html(msg["text"], pats)
                hit_mark = "🔥HIT" if is_hit_text(msg["text"], pats) else ""

                if jump and jump == (i, j):
                    st.markdown(
                        f"""
<div style="
background: #fff8dc;
border-left: 6px solid #ff9800;
padding: 12px;
margin: 10px 0;
border-radius: 6px;
color: #111;
">
<b>👇ジャンプ先 {j+1}. {role} {hit_mark}</b><br><br>
<div style="white-space: pre-wrap;">{text_html}</div>
</div>
""",
                        unsafe_allow_html=True,
                    )
                    st.caption(str(msg["create_time"]))
                    st.divider()
                else:
                    st.markdown(f"**{j+1}. {role} {hit_mark}**")
                    st.markdown(
                        f'<div style="white-space: pre-wrap;">{text_html}</div>',
                        unsafe_allow_html=True,
                    )
                    st.caption(str(msg["create_time"]))
                    st.divider()

else:
    st.info("まだ検索していません。クエリを入力して「検索」を押してください。")