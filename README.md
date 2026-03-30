# Conference Calendar

这个仓库现在采用“结构化数据 + 自动生成”的方式维护会议日历。

- 唯一数据源是 `data/conferences.yml`
- `conference_calendar.md`、`site/index.html`、`site/conference_calendar.ics`、`site/conference_calendar.json` 都是生成产物
- 每天会生成一个 GitHub Issue，用于提醒距离 deadline 还有 `30 / 14 / 7 / 3 / 1` 天的会议

## 我能收到哪些提醒

这个仓库目前有两种提醒方式：

1. `ICS 日历提醒`
   你把 `site/conference_calendar.ics` 订阅到自己的日历应用后，可以用 Google Calendar、Apple Calendar、Outlook 等客户端自己设置弹窗、邮件或系统提醒。

2. `GitHub Issue 提醒`
   仓库每天会自动维护一个 issue，标题格式固定为 `Deadline reminders for YYYY-MM-DD`，内容是当天命中的会议 deadline。

## 如果你只是想“收到提醒”

### 方式 1：订阅 ICS

1. 打开 GitHub Pages 页面。
2. 复制 `conference_calendar.ics` 链接。
3. 在你的日历客户端里选择“通过 URL 订阅日历”或类似功能。
4. 在日历客户端里给事件设置默认提醒。

说明：

- ICS 文件里既包含会议本身，也包含每一个具体的 registration / abstract deadline。
- 对 `TBA`、`open`、`?` 这类没有具体日期的 deadline，不会生成 ICS 事件，也不会自动提醒。

### 方式 2：接收 GitHub Issue 通知

如果你想收到每天的 GitHub deadline issue：

1. 打开仓库主页。
2. 点击右上角 `Watch`。
3. 选择 `Custom`。
4. 勾选 `Issues`。
5. 到你的 GitHub `Settings -> Notifications` 里确认 Web 或 Email 通知是开启的。

这样每天工作流更新或新建 reminder issue 时，你就能收到 GitHub 通知。

补充说明：

- reminder issue 使用固定标签 `deadline-reminder`
- 同一天重复运行工作流时，会更新同一个 issue，不会重复轰炸
- 如果仓库长期无活动，GitHub 可能暂停 scheduled workflows；这时重新启用 Actions 或手动运行一次工作流即可恢复

## 如果你是仓库维护者

### 1. 启用 GitHub Actions

这个仓库依赖三个工作流：

- `.github/workflows/ci.yml`
- `.github/workflows/deploy-pages.yml`
- `.github/workflows/deadline-reminders.yml`

你需要：

1. 在仓库的 `Actions` 页面启用 Actions。
2. 确认默认分支是 `main`。
3. 保持 `main` 分支上的工作流文件可执行。

### 2. 启用 GitHub Pages

这个仓库通过官方 Pages workflow 发布 `site/` 产物。

建议检查：

1. `Settings -> Pages`
2. Source 选择 `GitHub Actions`

完成后，`Deploy Pages` 工作流会自动发布生成的静态页面。

### 3. 手动触发一次初始化部署

首次启用后，建议手动运行两次工作流确认一切正常：

1. `Deploy Pages`
2. `Deadline Reminders`

这样你可以立即确认：

- Pages 页面是否可访问
- `conference_calendar.ics` 是否可下载
- reminder issue 是否成功创建

## 如何更新会议数据

只编辑：

- `data/conferences.yml`

不要手工编辑：

- `conference_calendar.md`

更新后本地执行：

```bash
python3 -m pip install -r requirements.txt
python3 scripts/build_calendar.py
python3 -m unittest discover -s tests -v
```

然后提交这些文件：

- `data/conferences.yml`
- `conference_calendar.md`
- `site/index.html`
- `site/conference_calendar.ics`
- `site/conference_calendar.json`

## Deadline reminder 的规则

- 只对有具体日期的 deadline 生效
- 检查窗口固定为 `30 / 14 / 7 / 3 / 1` 天前
- 业务日期按 `Europe/Berlin` 计算
- 每天只维护一个 issue

## 目录说明

- `data/conferences.yml`: 唯一真相源
- `scripts/build_calendar.py`: 生成 Markdown / HTML / ICS / JSON
- `scripts/build_reminders.py`: 生成每日 reminder issue payload
- `tests/`: 校验、生成、ICS、reminder 回归测试
- `site/`: GitHub Pages 发布产物
