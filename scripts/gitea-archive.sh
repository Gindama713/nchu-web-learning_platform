#!/usr/bin/env bash
# 校园网内运行；保留个人历史，不 mirror、不 force、不删除远端 ref。
# GITEA_URL=http://10.83.68.223:3000/g24201710/project.git \
# DOCS_REF=<检查1实际文档提交> bash scripts/gitea-archive.sh
set -euo pipefail
cd "$(dirname "$0")/.."
: "${GITEA_URL:?请设置课堂空仓库 URL}"
: "${DOCS_REF:?请指定实际通过检查1的文档提交，不自动用仓库初始提交冒充}"
DEV_REF="${DEV_REF:-origin/develop}"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "当前工作区不干净，请先定稿提交" >&2
  exit 1
fi
git fetch origin
dev_sha=$(git rev-parse "$DEV_REF^{commit}")
docs_sha=$(git rev-parse "$DOCS_REF^{commit}")
for path in README.md docs/PRD.md docs/APIC.md docs/ADR.md docs/CHG-RB.md docs/DBD.md; do
  git cat-file -e "$docs_sha:$path"
done
tag_checkpoint() {
  local name="$1" sha="$2"
  if git rev-parse -q --verify "refs/tags/$name" >/dev/null; then
    [[ "$(git rev-parse "$name^{commit}")" == "$sha" ]] || {
      echo "$name 已存在但指向其他提交；保留原 tag，请人工核对" >&2
      exit 1
    }
  else
    git tag -a "$name" "$sha" -m "课堂归档 $name"
  fi
}
tag_checkpoint checkpoint-1-docs "$docs_sha"
tag_checkpoint checkpoint-2-dev "$dev_sha"
if git remote get-url gitea >/dev/null 2>&1; then
  [[ "$(git remote get-url gitea)" == "$GITEA_URL" ]] || {
    echo "现有 gitea remote 与指定 URL 不一致，不自动改写" >&2
    exit 1
  }
else
  git remote add gitea "$GITEA_URL"
fi
git push gitea --all
git push gitea --tags
# --all 只推本地分支；若 develop 落后于刚获取的远端，用已选定的提交正常快进推送。
git push gitea "$dev_sha:refs/heads/develop"
failed=0
while read -r ref sha; do
  if [[ "$ref" == refs/heads/develop ]]; then sha="$dev_sha"; fi
  remote_sha=$(git ls-remote gitea "$ref" | awk '{print $1}')
  if [[ "$remote_sha" != "$sha" ]]; then
    echo "FAIL $ref local=$sha remote=$remote_sha" >&2
    failed=1
  else
    echo "OK $ref $sha"
  fi
done < <(git for-each-ref --format='%(refname) %(objectname)' refs/heads refs/tags)
[[ "$failed" == 0 ]]
echo "归档 ref 已逐项核对；将本次输出保存在课堂检查记录中。"
