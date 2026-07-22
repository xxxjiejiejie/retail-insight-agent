-- 仅用于本地 Docker 演示环境。生产环境必须从密钥管理系统注入强密码。
CREATE USER IF NOT EXISTS 'retail_readonly'@'%' IDENTIFIED BY 'readonly-local-dev';
GRANT SELECT ON retail_insight.* TO 'retail_readonly'@'%';
FLUSH PRIVILEGES;
