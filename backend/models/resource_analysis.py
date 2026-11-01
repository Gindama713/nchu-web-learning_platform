"""SPEC-003 resources dimension: usage statistics over real access events (R15)."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from backend.shared.api import parse_time, stamp

VERSION = "resources-usage-v1"


def extract(db, course_id, start, end, cutoff, subject):
    """读事务内提取课程资源、版本及时间范围内的真实访问事件。"""
    resources = [dict(row) for row in db.execute(
        "SELECT id,title,kind FROM resource WHERE course_id=? AND archived=0 ORDER BY id",
        (course_id,))]
    versions = [dict(row) for row in db.execute(
        "SELECT rv.id,rv.resource_id,rv.version FROM resource_version rv "
        "JOIN resource r ON r.id=rv.resource_id WHERE r.course_id=? AND r.archived=0 "
        "ORDER BY rv.resource_id,rv.version", (course_id,))]
    sql = ("SELECT e.user_id,e.resource_version_id,e.event_type,e.created_at "
           "FROM resource_event e JOIN resource_version rv ON rv.id=e.resource_version_id "
           "JOIN resource r ON r.id=rv.resource_id "
           "WHERE r.course_id=? AND e.created_at>=? AND e.created_at<=?")
    params = [course_id, start, end]
    if subject is not None:
        sql += " AND e.user_id=?"
        params.append(subject)
    events = [dict(row) for row in db.execute(sql + " ORDER BY e.id", params)]
    return {"resources": resources, "versions": versions, "events": events,
            "cutoff": cutoff, "subject": subject}


def metrics_for(snapshot, start, end, inclusive_end=False):
    """按事件时间区间计算指标；区间为左闭右开，末段（inclusive_end）包含上界。"""
    events = [e for e in snapshot["events"]
              if start <= e["created_at"] and (inclusive_end or e["created_at"] < end)]
    titles = {row["id"]: row["title"] for row in snapshot["resources"]}
    versions = {(row["id"]): row for row in snapshot["versions"]}
    per_version = {}
    for event in events:
        key = event["resource_version_id"]
        entry = per_version.setdefault(key, {"view_count": 0, "download_count": 0, "users": set()})
        entry[event["event_type"] + "_count"] += 1
        entry["users"].add(event["user_id"])
    items = []
    for version_id in sorted(per_version):
        entry = per_version[version_id]
        version = versions.get(version_id)
        if version is None:  # 事件指向的资源已归档，读取快照外则排除
            continue
        items.append({"resource_id": version["resource_id"],
                      "title": titles.get(version["resource_id"], ""),
                      "version_id": version_id, "version": version["version"],
                      "view_count": entry["view_count"],
                      "download_count": entry["download_count"],
                      "unique_users": len(entry["users"])})
    all_users = {event["user_id"] for event in events}
    return {
        "resource_count": len(snapshot["resources"]),
        "version_count": len(snapshot["versions"]),
        "view_count": sum(item["view_count"] for item in items),
        "download_count": sum(item["download_count"] for item in items),
        "unique_users": len(all_users),
        "items": items,
    }


def week_series(snapshot, start, end):
    """按上海周一 00:00 切分左闭右开区间，首尾裁剪到 from/to，末段含上界。"""
    shanghai = ZoneInfo("Asia/Shanghai")
    cursor = parse_time(start, "from")
    stop = parse_time(end, "to")
    rows = []
    while cursor < stop:
        local = cursor.astimezone(shanghai)
        next_monday = (local - timedelta(days=local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0) + timedelta(days=7)
        boundary = min(stop, next_monday.astimezone(cursor.tzinfo))
        rows.append({"period_start": stamp(cursor), "period_end": stamp(boundary),
                     "metrics": metrics_for(snapshot, stamp(cursor), stamp(boundary),
                                            inclusive_end=boundary >= stop)})
        cursor = boundary
    return rows


def calculate(snapshot, start, end, cutoff):
    overall = metrics_for(snapshot, start, end, inclusive_end=True)
    return {
        "dimension": "resources",
        "sample_size": overall["view_count"] + overall["download_count"],
        "metrics": overall,
        "series": week_series(snapshot, start, end),
        "source_until": cutoff,
        "population_basis": "resource_access_events",
        "unit": {"view_count": "count", "download_count": "count", "unique_users": "users"},
        "warnings": ["事件仅代表成功提供内容，不证明读完或保存完成"],
        "algorithm_version": VERSION,
    }
