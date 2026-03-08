import html
import json
import re
from pathlib import Path
from typing import Any

import streamlit as st

st.set_page_config(page_title="業務ナレッジ検索デモ V2", layout="wide")

DATA_DIR = Path(__file__).parent / "demo" / "demo_data"


@st.cache_data
def load_documents(data_dir: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for path in sorted(data_dir.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            docs.append(json.load(f))
    return docs


def normalize_text(text: str) -> str:
    return text.lower().strip()


def calc_score(doc: dict[str, Any], query: str) -> float:
    if not query:
        return 0.0

    q = normalize_text(query)

    title = normalize_text(str(doc.get("title", "")))
    summary = normalize_text(str(doc.get("summary", "")))
    content = normalize_text(str(doc.get("content", "")))
    tags = [normalize_text(str(tag)) for tag in doc.get("tags", [])]

    score = 0.0

    # 完全一致系
    if q == title:
        score += 20
    if q in title:
        score += 10
    if q in summary:
        score += 6
    if q in content:
        score += 4

    # 出現回数も加点
    score += title.count(q) * 3
    score += summary.count(q) * 2
    score += content.count(q) * 1

    # タグ一致は強めに加点
    for tag in tags:
        if q == tag:
            score += 8
        elif q in tag:
            score += 4

    return score


def highlight_text(text: str, query: str) -> str:
    escaped = html.escape(text)
    if not query:
        return escaped

    pattern = re.compile(re.escape(query), re.IGNORECASE)

    return pattern.sub(
        lambda m: f"<mark>{html.escape(m.group(0))}</mark>",
        escaped,
    )


def matches_category(doc: dict[str, Any], selected_category: str) -> bool:
    if selected_category == "すべて":
        return True
    return str(doc.get("category", "")) == selected_category


def search_documents(
    docs: list[dict[str, Any]],
    query: str,
    selected_category: str,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []

    for doc in docs:
        if not matches_category(doc, selected_category):
            continue

        if not query:
            score = 0.0
            filtered.append({**doc, "_score": score})
            continue

        score = calc_score(doc, query)
        if score > 0:
            filtered.append({**doc, "_score": score})

    if query:
        filtered.sort(
            key=lambda x: (
                x.get("_score", 0.0),
                str(x.get("date", "")),
                str(x.get("id", "")),
            ),
            reverse=True,
        )
    else:
        filtered.sort(
            key=lambda x: (
                str(x.get("date", "")),
                str(x.get("id", "")),
            ),
            reverse=True,
        )

    return filtered


def render_tags(tags: list[str]) -> str:
    if not tags:
        return "-"
    return " ".join([f"`#{tag}`" for tag in tags])


def main() -> None:
    st.title("業務ナレッジ検索デモ V2")
    st.caption("全文検索 + カテゴリ絞り込み + スコア表示 + 検索語ハイライト")

    docs = load_documents(DATA_DIR)

    with st.sidebar:
        st.header("検索条件")
        query = st.text_input("検索キーワード", placeholder="例: 検索、FAQ、手順")
        categories = sorted({str(doc.get("category", "")) for doc in docs if doc.get("category")})
        selected_category = st.selectbox("カテゴリ", ["すべて"] + categories)

        st.divider()
        st.markdown("**データ件数**")
        st.write(f"{len(docs)} 件")

    results = search_documents(docs, query, selected_category)

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("検索結果")
    with col2:
        st.metric("ヒット件数", len(results))

    if not results:
        st.warning("該当するデータがありません。検索条件を変えてください。")
        return

    for i, doc in enumerate(results, start=1):
        title = str(doc.get("title", "タイトルなし"))
        category = str(doc.get("category", "-"))
        date = str(doc.get("date", "-"))
        summary = str(doc.get("summary", ""))
        content = str(doc.get("content", ""))
        tags = doc.get("tags", [])
        score = float(doc.get("_score", 0.0))

        with st.container():
            st.markdown(f"### {i}. {title}")

            meta_col1, meta_col2, meta_col3 = st.columns([1, 1, 1])
            meta_col1.write(f"**カテゴリ:** {category}")
            meta_col2.write(f"**日付:** {date}")
            meta_col3.write(f"**Score:** {score:.1f}")

            st.write(f"**タグ:** {render_tags(tags)}")

            if summary:
                st.markdown("**概要**")
                st.markdown(
                    highlight_text(summary, query),
                    unsafe_allow_html=True,
                )

            st.markdown("**本文**")
            st.markdown(
                highlight_text(content, query),
                unsafe_allow_html=True,
            )

            if doc.get("public_note"):
                st.caption(f"公開メモ: {doc['public_note']}")

            st.divider()


if __name__ == "__main__":
    main()