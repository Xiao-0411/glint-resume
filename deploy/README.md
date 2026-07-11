# sgjl.cloud 部署说明

推荐部署结构：

```text
https://sgjl.cloud        -> Vue 前端 dist 静态文件
https://sgjl.cloud/api/*  -> FastAPI 后端 127.0.0.1:8000
```

## 1. DNSPod 解析

在 DNSPod / 腾讯云 DNS 里添加两条 A 记录：

```text
主机记录: @
记录类型: A
记录值: 你的服务器公网 IP

主机记录: www
记录类型: A
记录值: 你的服务器公网 IP
```

## 2. 放通端口

服务器安全组或轻量应用服务器防火墙需要放通：

```text
80/tcp
443/tcp
```

后端 `8000` 建议只监听 `127.0.0.1`，不直接暴露公网。

## 3. 构建前端

本地或服务器上执行：

```bash
cd frontend
npm run build
```

把 `frontend/dist` 上传到服务器：

```text
/var/www/sgjl.cloud/dist
```

## 4. 启动后端

后端建议监听本机地址：

```bash
cd backend
./.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

生产环境建议用 systemd、Supervisor 或 Docker 托管后端进程。

## 5. Nginx 反向代理

把 `deploy/nginx/sgjl.cloud.conf` 放到服务器：

```text
/etc/nginx/sites-available/sgjl.cloud.conf
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/sgjl.cloud.conf /etc/nginx/sites-enabled/sgjl.cloud.conf
sudo nginx -t
sudo systemctl reload nginx
```

## 6. HTTPS 证书

如果用 Let's Encrypt + Certbot：

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d sgjl.cloud -d www.sgjl.cloud
```

证书签发成功后，确认自动续期：

```bash
sudo certbot renew --dry-run
```

## 7. 验证

```bash
curl -I https://sgjl.cloud
curl https://sgjl.cloud/api/health
```

如果 `https://sgjl.cloud/api/health` 返回 `{"status":"ok",...}`，说明反向代理和 HTTPS 已经通了。
