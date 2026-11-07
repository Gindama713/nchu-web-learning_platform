"""手势图案签到用到的校验与比对。

3×3 九宫格，九个点按行优先编号 0-8（左上角 0，右下角 8）。前端上报的是
点的序列，这里统一规范化成 "0-1-2-5-8" 这样的字符串，再交给 Werkzeug 的
口令哈希器存储与比对——图案本身不落库。
"""

from werkzeug.security import check_password_hash, generate_password_hash

from backend.shared.api import ApiError

MIN_POINTS = 4
MAX_POINTS = 9


def pattern_text(value):
    """校验并规范化图案；不合法直接抛 422。

    至少连 4 个点、最多 9 个，同一点不能走两次——和手机手势密码的规则
    一致，否则来回划两下的图案也能当密码用。
    """
    if not isinstance(value, list) or not MIN_POINTS <= len(value) <= MAX_POINTS:
        raise ApiError(422, "VALIDATION_ERROR",
                       f"手势至少要连接 {MIN_POINTS} 个点，最多 {MAX_POINTS} 个")
    walked = []
    for point in value:
        if isinstance(point, bool) or not isinstance(point, int) or not 0 <= point <= 8:
            raise ApiError(422, "VALIDATION_ERROR", "手势点必须是 0-8 的整数")
        if point in walked:
            raise ApiError(422, "VALIDATION_ERROR", "同一个点不能连接两次")
        walked.append(point)
    return "-".join(str(point) for point in walked)


def pattern_hash(value):
    return generate_password_hash(pattern_text(value))


def pattern_matches(stored, value):
    """没有录入过图案、或图案不合法，都算不匹配，不抛异常。"""
    if not stored:
        return False
    try:
        return check_password_hash(stored, pattern_text(value))
    except ApiError:
        return False
