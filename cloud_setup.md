# Cloud QQ Bot Setup

这份说明用于把项目放到一台 24 小时在线的 Ubuntu 云服务器上，让它每天自动更新 Fortnite 商店图片，并通过 NapCatQQ 的 OneBot HTTP 发到 QQ 群。

## 你需要准备

- 一台 Ubuntu 22.04 或 24.04 云服务器
- 一个 QQ 小号，用来登录 NapCatQQ
- QQ 群号
- 当前 GitHub 仓库地址

仓库地址：

```text
https://github.com/wolping13-png/fortnite-daily-shop
```

## 1. 安装基础环境

SSH 登录服务器后运行：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip cron curl
```

## 2. 下载项目

```bash
git clone https://github.com/wolping13-png/fortnite-daily-shop.git
cd fortnite-daily-shop
```

如果你已经下载过：

```bash
cd fortnite-daily-shop
git pull
```

## 3. 配置 QQ 群

复制配置文件：

```bash
cp qq_bot_config.example.json qq_bot_config.json
nano qq_bot_config.json
```

把里面改成你的实际信息：

```json
{
  "onebot_http_url": "http://127.0.0.1:3000",
  "access_token": "",
  "group_ids": [
    123456789
  ],
  "caption": "Fortnite Daily Shop",
  "image_url": ""
}
```

如果 NapCatQQ 和这个项目在同一台服务器，`onebot_http_url` 通常就是：

```text
http://127.0.0.1:3000
```

如果你在 NapCatQQ 里设置了 access token，就填到 `access_token`。

## 4. 部署 NapCatQQ

在服务器上安装并启动 NapCatQQ，然后登录机器人 QQ 小号。

NapCatQQ 官方项目：

```text
https://github.com/NapNeko/NapCatQQ
```

NapCatQQ 的 OneBot 网络说明：

```text
https://www.napcat.wiki/onebot/network
```

需要确认：

- 机器人 QQ 已经登录
- 机器人 QQ 已加入目标 QQ 群
- OneBot HTTP 已开启
- 端口和 `qq_bot_config.json` 一致，例如 `3000`

安全建议：OneBot HTTP 端口尽量只监听 `127.0.0.1`，不要直接暴露到公网。

## 5. 手动测试一次

在项目目录运行：

```bash
bash run_daily_qq.sh
```

成功后，QQ 群里应该会收到一条文字和一张 `shop.png`。

如果失败，先看错误信息。常见原因：

- NapCatQQ 没启动
- 机器人 QQ 没登录
- 群号填错
- OneBot HTTP 端口不对
- access token 不一致

## 6. 安装每天自动发送

确认手动测试成功后运行：

```bash
bash install_cloud_cron.sh
```

默认会安装一个 cron 任务：

```text
15 0 * * *
```

服务器通常使用 UTC 时间，所以 `00:15 UTC` 对应北京时间 `08:15`。

日志位置：

```text
logs/qq_daily.log
```

查看日志：

```bash
tail -n 100 logs/qq_daily.log
```

## 7. 修改发送时间

如果想改时间，可以用 `CRON_TIME`：

```bash
CRON_TIME="30 0 * * *" bash install_cloud_cron.sh
```

这表示每天 UTC 00:30，也就是北京时间 08:30。

## 8. 更新项目

以后如果本项目有更新：

```bash
cd fortnite-daily-shop
git pull
bash install_cloud_cron.sh
```

## 重要提醒

NapCatQQ 属于第三方 QQ 协议端方案。建议使用 QQ 小号，并避免高频发送消息。下载安装到服务器后，账号登录和风控风险需要你自己判断。
