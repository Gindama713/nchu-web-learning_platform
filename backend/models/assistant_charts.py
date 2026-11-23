"""教学助手的图表数据：只给结构化数字，不给颜色、不生成 SVG。

三条约束（写在这里，改代码前先看）：
1. 数字同源：调用方必须把「已经算进 facts 的那份结果」传进来，不许为画图再查一次库，
   否则会出现「文字说 30%、图显示 35%」。
2. 空就不给：环形 total=0、条形一项没有、折线少于 2 点，直接返回 None，让界面不画空占位。
3. 每答最多 2 张：按调用方给的顺序截断，避免回答变成仪表盘。

颜色由前端按 colorKey 映射 chartColors，服务端不认识颜色。
"""

MAX_CHARTS = 2


def donut(title, slices, unit="人次"):
    """环形图。0 值项保留在图例里——「没有迟到、没有请假」本身是结论。"""
    rows = [{"label": row["label"], "value": row["value"], "colorKey": row["colorKey"]}
            for row in slices if row["value"] is not None]
    total = sum(row["value"] for row in rows if row["value"] > 0)
    if not total:
        return None
    return {"kind": "donut", "title": title, "unit": unit, "total": total, "slices": rows}


def bars(title, items, unit="percent", max_value=100):
    """横向条形。用于「按知识点比高低」这类长标签，值按 max_value 归一。"""
    rows = []
    for item in items:
        value = item["value"]
        if value is None:
            continue
        rows.append({"label": item["label"], "value": value,
                     "colorKey": item.get("colorKey", "accent"),
                     "note": item.get("note", "")})
    if not rows:
        return None
    return {"kind": "bar", "title": title, "unit": unit, "max": max_value, "items": rows}


def line(title, points, unit="ratio", max_value=1):
    """折线。少于 2 个点画不出趋势，直接不给。"""
    rows = [{"label": point["label"], "value": point["value"]}
            for point in points if point["value"] is not None]
    if len(rows) < 2:
        return None
    return {"kind": "line", "title": title, "unit": unit, "max": max_value, "points": rows}


def limit(charts):
    """去掉 None，按顺序最多留 MAX_CHARTS 张。"""
    kept = [chart for chart in charts if chart]
    return kept[:MAX_CHARTS]
