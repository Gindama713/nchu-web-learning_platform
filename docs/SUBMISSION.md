# 结课提交操作说明

按任务书附件，组长提交名单、Word 报告与源码设计 ZIP，成员分别提交「学号_姓名_设计报告.docx」。目前以报告中的 242017 班、第 10 组作为默认值，最终上传前核对教学班写法。

在仓库根目录、安装 python-docx 的 Python 环境中执行：

```sh
python scripts/package_submission.py --class-name 242017 --group 10 --output test-tmp/submission-preview
python scripts/verify_submission.py test-tmp/submission-preview
```

输出 `242017班_第10组_成员名单.txt`、`242017班_第10组_大作业报告.docx` 与 SHA256 核对清单。输出目录须为新目录，避免覆盖旧版本。报告含封面、Word TOC 目录域和页脚 PAGE 域；用 Word 全选按 F9 更新目录并保存，逐页检查后通过 `--report-docx docs/reports/g24201710_小组大作业报告.docx` 将成稿复制进新包，摘要自动按成稿生成。

源码先完成提交并保持工作区干净，再执行：

```sh
python scripts/package_submission.py --class-name 242017 --group 10 --output test-tmp/submission-final --include-source
python scripts/verify_submission.py test-tmp/submission-final --require-source
```

源码包只收 `git ls-files` 跟踪文件，排除数据库、凭据、运行数据与依赖目录；新材料必须先提交才会入包。它是源码归档，不包含 Git 历史，不能替代 Gitea 的独立个人提交记录。核对清单的 `source_commit` 标记生成时 HEAD；未带源码的预览可能包含未提交报告改动。

机器检查只证明命名、摘要、ZIP 与 Word 域结构，不自动判断截图打码效果、目录分页、本人材料确认、教师验收或超星上传回执。上传前检查截图中的姓名、学号、Cookie 与令牌，并确认 Gitea 分支与 checkpoint tag 的远端 SHA。

校园归档脚本为 `scripts/gitea-archive.sh`，运行前提供 `GITEA_URL` 与实际检查1文档提交 `DOCS_REF`；脚本先 fetch，再为 origin/develop 建检查2 tag，逐 ref 核对 SHA。现存同名 tag 指向不同提交时停止，不改写历史。`--all` 推送本地分支，不会自动把仅存在于 origin 的每个分支转换成本地分支。

## 尚需人工闭环

石佰合的材料由本轮按代码协助整理，须本人复核并独立提交；课堂截图及 CP-4 双浏览器记录须现场执行。校园 Gitea 与超星上传需要校园网络和对应账号，本地生成文件不等于已提交。
