# Fortnite Daily Shop

一个可以部署到 GitHub Pages 的 Fortnite 每日商城静态网页项目。

页面会读取 `shop.json`，用手机友好的卡片布局展示每日商城物品，包括名称、稀有度、价格、图片和分区名称。`update_shop.py` 会请求 `https://fortnite-api.com/v2/shop` 并生成最新的 `shop.json`。

## 一键发布

Windows 上可以直接双击：

```text
one-click-publish.bat
```

或者在 PowerShell 里运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\publish.ps1
```

默认会创建公开仓库 `fortnite-daily-shop`。如果想换仓库名：

```powershell
powershell -ExecutionPolicy Bypass -File .\publish.ps1 -RepoName "my-fortnite-shop"
```

脚本会自动做这些事：

- 检查 Git、Python、GitHub CLI。
- 登录 GitHub CLI，如果没登录会打开浏览器让你登录。
- 安装 Python 依赖并检查 `update_shop.py`。
- 尝试生成一次真实 `shop.json`。
- 初始化 Git 仓库并提交文件。
- 创建 GitHub 仓库并推送代码。
- 开启 GitHub Pages。
- 触发一次 GitHub Actions，马上更新商城数据。

如果脚本提示缺少 GitHub CLI，请先安装：

```text
https://cli.github.com/
```

安装后运行：

```powershell
gh auth login
```

然后再运行 `publish.ps1`。

## 本地预览

安装依赖：

```bash
pip install -r requirements.txt
```

生成或刷新 `shop.json`：

```bash
python update_shop.py
```

启动本地预览：

```bash
python -m http.server 8000
```

打开：

```text
http://localhost:8000
```

## 自动更新

项目已经包含 GitHub Actions 工作流：

```yaml
schedule:
  - cron: "5 0 * * *"
workflow_dispatch:
```

GitHub Actions 使用 UTC 时间。`00:05 UTC` 对应北京时间 `08:05`，所以商城会每天北京时间 8:05 自动更新。

`workflow_dispatch` 已开启，可以在 GitHub 仓库的 `Actions` 页面手动点击 `Run workflow` 更新。

## 文件说明

- `index.html`：静态页面。
- `update_shop.py`：请求 Fortnite API 并生成 `shop.json`。
- `shop.json`：页面读取的商城数据。
- `requirements.txt`：Python 依赖。
- `publish.ps1`：一键发布脚本。
- `.github/workflows/update-shop.yml`：每日自动更新和手动更新流程。

## 常见问题

如果页面打开后暂时没有数据，去 GitHub 仓库的 `Actions` 页面查看 `Update Fortnite Shop` 是否运行完成。第一次发布后 GitHub Pages 和 Actions 都可能需要等几分钟。

如果 Actions 没有权限提交 `shop.json`，进入仓库 `Settings` -> `Actions` -> `General`，把 `Workflow permissions` 改成 `Read and write permissions`。
