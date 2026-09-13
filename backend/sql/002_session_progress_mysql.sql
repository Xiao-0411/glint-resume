-- 板块式对话:记录每个会话的板块完成情况与简历板块顺序。
-- 后端启动时 init_db() 会自动补齐该列;手动升级可执行本文件。

USE glint;

ALTER TABLE sessions ADD COLUMN progress JSON NULL;
