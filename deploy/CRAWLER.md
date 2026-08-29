# 云服务器爬虫常驻部署

当前爬虫不是 FastAPI 的一部分。`uvicorn main:app` 只启动接口服务，职位抓取由
`backend/run_crawler.py` 独立运行。三个招聘平台还依赖服务器本机
`127.0.0.1:9222` 上的已登录 Chrome，因此只迁移后端进程不会自动迁移本地的
Chrome 登录态。

本文支持 OpenCloudOS/RHEL 系和 Ubuntu/Debian 系。以下命令默认在服务器执行；
已经是 `root` 时不需要再加 `sudo`。

## 1. 识别系统和真实部署位置

先执行只读检查，不要提前创建 `/opt/sgjl` 等示例目录：

```bash
cat /etc/os-release
command -v dnf || command -v yum || command -v apt-get
ps -eo user,pid,args | grep -E '[u]vicorn|[g]unicorn|[p]ython.*main:app'
systemctl list-units --type=service --all | grep -Ei 'glint|sgjl|uvicorn|gunicorn|fastapi'
find /opt /srv /www /var/www /data /root /home -type f -path '*/backend/run_crawler.py' 2>/dev/null
command -v docker >/dev/null && docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Command}}'
command -v podman >/dev/null && podman ps --format 'table {{.Names}}\t{{.Image}}\t{{.Command}}'
```

`find` 返回路径如 `/data/apps/resume/backend/run_crawler.py` 时，真实项目目录就是
`/data/apps/resume`。如果后端正在运行，`ps` 第一列就是目前的运行用户。也可以用
进程 PID 继续确认：

```bash
readlink -f /proc/后端PID/cwd
```

如果后端位于 Docker/Podman 容器而不在宿主机目录中，不要继续使用本文的宿主机
systemd 安装器；应在现有 Compose/容器部署中增加 Chrome 和 crawler 服务。

后续统一用两个 shell 变量，必须替换成上一步查到的真实值：

```bash
APP_DIR=/真实项目绝对路径
SERVICE_USER=真实的非root后端运行用户
test -f "$APP_DIR/backend/run_crawler.py"
id "$SERVICE_USER"
```

两个检查都成功后才能继续。不要让 Chrome 和爬虫长期以 `root` 运行；如果现有后端
就是 root，先创建专用系统用户，并把项目或运行所需目录权限授予它：

```bash
useradd --system --create-home --shell /sbin/nologin glint
SERVICE_USER=glint
chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"
```

最后一条会改变整个项目目录的所有者，只适用于该目录专门用于部署且没有其他服务
共用的情况。目录共用时应逐项授权，不要直接执行递归 `chown`。

## 2. 安装系统依赖

OpenCloudOS、TencentOS、Rocky、AlmaLinux、CentOS Stream 等使用 `dnf`：

```bash
dnf install -y xorg-x11-server-Xvfb
dnf search x11vnc chromium
dnf install -y x11vnc
```

部分 OpenCloudOS 镜像的默认仓库不提供 `x11vnc`。若搜索不到，不要下载来源不明的
RPM；先运行 `dnf repolist all` 确认云厂商提供的扩展仓库，或改用该系统仓库中的
TigerVNC。Ubuntu/Debian 才使用：

```bash
apt-get update
apt-get install -y xvfb x11vnc
```

还需要 Google Chrome 或 Chromium。先检查服务器架构和现有浏览器：

```bash
uname -m
command -v google-chrome-stable || command -v google-chrome || \
  command -v chromium || command -v chromium-browser || command -v ungoogled-chromium
```

如果没有浏览器，需要按当前发行版和 CPU 架构安装。安装脚本只识别上面五个命令，
不会自行下载浏览器。

在 OpenCloudOS 上先查看仓库搜索结果，不要假设 `x11vnc` 或 `chromium` 一定存在：

```bash
dnf repolist
dnf search x11vnc chromium
```

## 3. 安装 systemd 服务

项目中必须已有 Linux 虚拟环境 `backend/.venv`。Windows 上传过来的
`.venv/Scripts/python.exe` 不能在 Linux 使用；缺少时执行：

```bash
cd "$APP_DIR/backend"
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

确认 `backend/.env` 的 `DATABASE_URL` 与 Web 后端使用同一个数据库，然后安装：

```bash
cd "$APP_DIR"
bash deploy/systemd/install.sh "$APP_DIR" "$SERVICE_USER"
```

安装器会创建三个服务，并先将显示器和 Chrome 设为开机自启：

```text
glint-crawler-display.service  Xvfb 虚拟显示器
glint-crawler-browser.service  持久化登录 Chrome，CDP 只监听 127.0.0.1:9222
glint-crawler.service          backend/run_crawler.py 调度器
```

## 4. 首次登录三个平台

先只启动显示器和浏览器：

```bash
systemctl start glint-crawler-display glint-crawler-browser
curl http://127.0.0.1:9222/json/version
```

在服务器终端启动临时 VNC。它只监听服务器本机，不要在安全组开放 `5900`：

```bash
runuser -u "$SERVICE_USER" -- x11vnc -display :99 -localhost -shared -forever
```

在本地 Windows PowerShell 建立 SSH 隧道：

```powershell
ssh -L 5900:127.0.0.1:5900 服务器登录用户@服务器公网IP
```

用本地 VNC 客户端连接 `127.0.0.1:5900`。再开一个服务器终端，让项目脚本打开并
检查三个招聘网站：

```bash
runuser -u "$SERVICE_USER" -- bash -c \
  "cd '$APP_DIR/backend' && ./.venv/bin/python scripts/monitor_recruitment_logins.py --cdp-port 9222 --timeout 1800"
```

在 VNC 窗口中分别登录 BOSS 直聘、智联招聘和猎聘。监控脚本显示三个平台全部
`OK` 后，可以结束 `x11vnc` 和 SSH 隧道；不要停止 Chrome 服务。登录信息保存在
服务用户的 `~/.boss-zhipin-scraper/chrome-profile`，服务器重启后仍会复用。
这个目录由安装器设置为仅服务用户可访问，部署和备份时不要放宽其权限。
监控脚本退出时会关闭它临时打开的三个页面，但不会清除登录态；之后由常驻调度器
为每个平台各保留一个爬取页面。

登录监控只是诊断工具，不是常驻爬虫。它会一直等待到三个平台同时通过严格检查，
状态不变不代表进程死锁。某个平台受风控而长期 `WAIT` 时可以按 `Ctrl+C` 结束监控；
调度器会分别运行三个平台，一个平台失败不会阻止其他平台入库。

调度器运行时每个平台的搜索任务只保留一个 CDP 标签页，切换城市或关键词时复用该页
导航；一轮结束会关闭 crawler 创建的页面，Chrome 自带的 `about:blank` 不属于爬虫页面。
列表卡片必须同时有岗位名称、可识别薪资、城市地点和真实公司名才允许入库；不完整卡片
会在日志中记录 `job_rejected_quality` 并跳过，BOSS、智联、猎聘三个平台均在最终写库处
再次执行这个质量闸门。

## 5. 启动并验证常驻爬虫

首次验证建议暂时把 `backend/.env` 中 `CRAWLER_MAX_CITIES` 和
`CRAWLER_MAX_KEYWORDS` 都设为 `1`，并把 `JD_BACKFILL_ENABLED` 设为 `false`。
默认的 `4 城市 × 5 关键词` 加 JD 补全可能让单轮持续数十分钟。小范围验证成功后
再恢复生产值并重启爬虫。

```bash
systemctl enable --now glint-crawler
systemctl status glint-crawler-display glint-crawler-browser glint-crawler
journalctl -u glint-crawler -f
```

确认日志依次出现 `crawler_scheduler_started`、`crawler_start` 和
`crawler_done`/`jobs_saved`。重启服务器后验证开机自启：

```bash
reboot
# 重新连接后
systemctl is-active glint-crawler-display glint-crawler-browser glint-crawler
curl http://127.0.0.1:9222/json/version
```

API 的 `/api/jobs/crawler-status` 需要登录态，可从管理页面查看每个平台的最后开始
时间、完成时间和错误。`systemctl active` 只代表调度器进程存活；如果招聘网站登录
过期，进程仍在，但平台状态会变成失败，此时重复第 4 节重新登录。

## 6. 常用排错

```bash
journalctl -u glint-crawler -n 200 --no-pager
journalctl -u glint-crawler-browser -n 100 --no-pager
systemctl restart glint-crawler-browser
systemctl restart glint-crawler
```

- `Connection refused 127.0.0.1:9222`：Chrome 服务未运行或没有成功启动。
- `登录状态已失效`、页面无职位：通过 SSH + VNC 重新登录对应平台。
- Chrome 频繁退出：检查服务器内存；小内存实例应增加 swap，并查看浏览器日志。
- 本地能抓、云端持续被拦截：招聘平台可能限制云机房 IP。进程守护无法解决 IP
  风控，需要更换合规的数据源、使用平台开放 API，或把爬虫保留在稳定的住宅网络
  机器上并只把结果写入云数据库。

CDP 端口不得监听公网，也不要开放 `9222` 或 `5900` 的安全组入站规则。
