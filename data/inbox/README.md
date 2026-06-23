# Inbox

这里放待审核线索，不放已确认岗位。

适合放：

- 牛客发现的 URL 或标题池
- 公众号文章 URL 列表
- 就业群复制文本
- 腾讯文档导出的 CSV/TSV

推荐流程：

```bash
python3 scripts/import_feed.py --preset group --inbox data/inbox --review-html
python3 scripts/import_feed.py --review-json job_import_review.json
```

牛客专项：

```bash
python3 scripts/nowcoder_discover.py --limit-per-keyword 6 --replace
python3 scripts/import_feed.py --preset nowcoder --text data/inbox/nowcoder_discovered.txt --review-html data/import_preview_nowcoder.html
```

审核前的线索不等于正式岗位；补齐公司、岗位、截止日期和官网/投递链接后再入库。
