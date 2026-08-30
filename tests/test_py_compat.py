"""Python 版本兼容性守卫。

背景：学生的 macOS 自带 python 3.9.6，装完依赖后只卡在版本检查这一步。
排查后发现——**本仓库根本没用到 3.10+ 的运行时特性**，那条 `>= 3.10` 是拍脑袋定的。

于是把下限降到 3.9，并写下这组测试：
以后谁不小心写了 `match` 语句或运行时的 `X | Y`，测试会立刻红，
而不是等某个学生在自己电脑上撞墙。

> 教学要点：**依赖门槛也是接口的一部分。**
> 每提高一个版本下限，就有一批人被挡在门外；
> 提之前先确认"我真的用到了那个版本的特性吗"。
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY_FILES = sorted(
    list((REPO / "scripts").rglob("*.py"))
    + list((REPO / "tools").glob("*.py"))
    + list((REPO / "tests").glob("*.py"))
)

# 3.10+ 才有的标准库 API，用了就等于把下限抬上去
PY310_APIS = ("itertools.pairwise", "bit_count(", "kw_only=True", "slots=True")


def _rel(f: Path) -> str:
    return str(f.relative_to(REPO))


def test_repo_has_python_files():
    assert len(PY_FILES) > 20


def test_no_match_statement():
    """match 语句是 3.10+ 独有语法，会让 3.9 直接 SyntaxError。"""
    bad = [_rel(f) for f in PY_FILES
           if any(isinstance(n, ast.Match)
                  for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))))]
    assert not bad, f"这些文件用了 match 语句，会把 Python 下限抬到 3.10：{bad}"


def test_union_annotations_need_future_import():
    """`str | None` 这类注解在 3.9 上会炸，除非文件顶部有 from __future__ import annotations。"""
    bad = []
    for f in PY_FILES:
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        if any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
               and any(a.name == "annotations" for a in n.names) for n in tree.body):
            continue
        for n in ast.walk(tree):
            for attr in ("annotation", "returns"):
                a = getattr(n, attr, None)
                if a is None:
                    continue
                seg = ast.get_source_segment(src, a) or ""
                if "|" in seg:
                    bad.append(f"{_rel(f)}:{getattr(n, 'lineno', '?')} {seg[:40]}")
    assert not bad, ("下面的文件缺 `from __future__ import annotations` 却用了 X | Y 注解，"
                     f"在 Python 3.9 上会报错：\n" + "\n".join(bad[:10]))


def test_no_python310_only_stdlib():
    me = Path(__file__).name
    bad = []
    for f in PY_FILES:
        if f.name == me:          # 本文件自身就写着这些关键词
            continue
        src = f.read_text(encoding="utf-8")
        for api in PY310_APIS:
            if api in src:
                bad.append(f"{_rel(f)} → {api}")
    assert not bad, f"用了 3.10+ 才有的 API：{bad}"


def test_declared_floor_matches_reality():
    """三处声明的 Python 下限必须一致：doctor / requirements.txt / AGENTS.md。"""
    import sys

    sys.path.insert(0, str(REPO / "tools"))
    import astock

    assert astock.MIN_PY == (3, 9)
    assert "Python >= 3.9" in (REPO / "requirements.txt").read_text(encoding="utf-8"), \
        "requirements.txt 顶部要写清最低版本"
    assert "Python >= 3.9" in (REPO / "AGENTS.md").read_text(encoding="utf-8")
