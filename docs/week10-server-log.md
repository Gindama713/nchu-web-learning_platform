# 第10周 用户访问日志记录

- 小组：g24201710（计算机组成原理组，242017 班）
- 导出时间：2026-11-01 17:07:57
- 日志区间：2026-11-01 17:04:55 — 2026-11-01 17:07:14
- 统计口径：`access_log` 表按每次 HTTP 请求记一条，含登录前的匿名请求；导出脚本为 `scripts/export_week10_docs.py`，可用 `python scripts/export_week10_docs.py` 复现。

## 1 概览

| 指标 | 数值 |
|---|---|
| 请求总数 | 76 |
| 有登录身份的账号数 | 2 |
| 失败请求（状态码 ≥ 400） | 4 |

## 2 按账号统计

| 学号 | 姓名 | 角色 | 请求数 | 失败数 | 最近访问 |
|---|---|---|---|---|---|
| teacher | 演示教师 | teacher | 49 | 0 | 2026-11-01 17:07:14 |
| 24201716 | 黄俊诚 | student | 24 | 2 | 2026-11-01 17:06:14 |

## 3 访问最多的接口

| 方法 | 路径 | 次数 |
|---|---|---|
| GET | /api/v1/courses | 16 |
| GET | /api/v1/auth/session | 12 |
| GET | /api/v1/courses/15/members | 10 |
| GET | /api/v1/courses/15/analytics | 6 |
| POST | /api/v1/auth/login | 6 |
| GET | /api/v1/courses/15/attendance-records | 4 |
| GET | /api/v1/courses/15/attendance-tasks | 4 |
| GET | /api/v1/courses/15/leave-requests | 4 |
| GET | /api/v1/courses/15/warnings | 4 |
| GET | /api/v1/notifications | 4 |
| GET | /api/v1/attendance-tasks/50/seats | 2 |
| GET | /api/v1/courses/15/warning-runs | 2 |
| POST | /api/v1/auth/logout | 2 |

## 4 失败请求明细

权限隔离与限流的直接证据，按时间倒序最多列 30 条。

| 时间 | 学号 | 方法 | 路径 | 状态 |
|---|---|---|---|---|
| 2026-11-01 17:06:14 | 24201716 | GET | /api/v1/courses/15/members | 403 |
| 2026-11-01 17:05:58 | 未登录 | GET | /api/v1/auth/session | 401 |
| 2026-11-01 17:05:46 | 24201716 | GET | /api/v1/courses/15/members | 403 |
| 2026-11-01 17:05:30 | 未登录 | GET | /api/v1/auth/session | 401 |

## 5 最近访问明细

| 时间 | 学号 | 姓名 | 方法 | 路径 | 状态 | 耗时(ms) |
|---|---|---|---|---|---|---|
| 2026-11-01 17:07:14 | teacher | 演示教师 | POST | /api/v1/auth/login | 200 | 289.6 |
| 2026-11-01 17:06:14 | 24201716 | 黄俊诚 | GET | /api/v1/courses/15/members | 403 | 36.2 |
| 2026-11-01 17:06:13 | 24201716 | 黄俊诚 | GET | /api/v1/courses/15/analytics | 200 | 52.5 |
| 2026-11-01 17:06:13 | 24201716 | 黄俊诚 | GET | /api/v1/courses | 200 | 21.9 |
| 2026-11-01 17:06:13 | 24201716 | 黄俊诚 | GET | /api/v1/courses | 200 | 20.9 |
| 2026-11-01 17:06:13 | 24201716 | 黄俊诚 | GET | /api/v1/auth/session | 200 | 9.4 |
| 2026-11-01 17:06:13 | 24201716 | 黄俊诚 | GET | /api/v1/auth/session | 200 | 62.8 |
| 2026-11-01 17:06:13 | 24201716 | 黄俊诚 | GET | /api/v1/courses/15/attendance-tasks | 200 | 49.5 |
| 2026-11-01 17:06:13 | 24201716 | 黄俊诚 | GET | /api/v1/courses/15/attendance-records | 200 | 33.9 |
| 2026-11-01 17:06:13 | 24201716 | 黄俊诚 | GET | /api/v1/courses/15/leave-requests | 200 | 18.5 |
| 2026-11-01 17:06:13 | 24201716 | 黄俊诚 | GET | /api/v1/notifications | 200 | 23.5 |
| 2026-11-01 17:06:13 | 24201716 | 黄俊诚 | GET | /api/v1/courses | 200 | 11.1 |
| 2026-11-01 17:06:13 | 24201716 | 黄俊诚 | POST | /api/v1/auth/login | 200 | 286.5 |
| 2026-11-01 17:06:11 | teacher | 演示教师 | POST | /api/v1/auth/logout | 204 | 16.7 |
| 2026-11-01 17:06:08 | teacher | 演示教师 | GET | /api/v1/attendance-tasks/50/seats | 200 | 9.5 |
| 2026-11-01 17:06:08 | teacher | 演示教师 | GET | /api/v1/courses | 200 | 10.9 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/courses/15/warning-runs | 200 | 8.8 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/courses/15/warnings | 200 | 9.3 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/courses/15/members | 200 | 8.9 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/courses/15/members | 200 | 10.0 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/courses/15/members | 200 | 81.7 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/courses/15/analytics | 200 | 116.1 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/courses/15/analytics | 200 | 32.2 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/courses | 200 | 12.0 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/courses | 200 | 11.3 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/courses | 200 | 62.2 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/auth/session | 200 | 8.6 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/auth/session | 200 | 12.8 |
| 2026-11-01 17:06:06 | teacher | 演示教师 | GET | /api/v1/auth/session | 200 | 11.0 |
| 2026-11-01 17:06:03 | teacher | 演示教师 | GET | /api/v1/courses/15/attendance-records | 200 | 91.0 |
| 2026-11-01 17:06:03 | teacher | 演示教师 | GET | /api/v1/courses/15/warnings | 200 | 75.3 |
| 2026-11-01 17:06:03 | teacher | 演示教师 | GET | /api/v1/courses/15/members | 200 | 59.7 |
| 2026-11-01 17:06:03 | teacher | 演示教师 | GET | /api/v1/courses/15/leave-requests | 200 | 45.5 |
| 2026-11-01 17:06:03 | teacher | 演示教师 | GET | /api/v1/courses/15/attendance-tasks | 200 | 29.3 |
| 2026-11-01 17:06:03 | teacher | 演示教师 | GET | /api/v1/notifications | 200 | 37.5 |
| 2026-11-01 17:06:03 | teacher | 演示教师 | GET | /api/v1/courses | 200 | 9.8 |
| 2026-11-01 17:06:03 | teacher | 演示教师 | POST | /api/v1/auth/login | 200 | 292.3 |
| 2026-11-01 17:05:58 | — | — | GET | /api/v1/auth/session | 401 | 0.1 |
| 2026-11-01 17:05:46 | 24201716 | 黄俊诚 | GET | /api/v1/courses/15/members | 403 | 8.9 |
| 2026-11-01 17:05:46 | 24201716 | 黄俊诚 | GET | /api/v1/courses | 200 | 36.3 |

> 完整日志可在线导出：`GET /api/v1/logs/access.csv`（教师/管理员）或 `GET /api/v1/logs/access`（JSON）。
