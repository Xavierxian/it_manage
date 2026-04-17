-- 定时任务监控表
CREATE TABLE IF NOT EXISTS cron_job_monitor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    job_name VARCHAR(255) NOT NULL COMMENT '任务名称',
    server_ip VARCHAR(50) NOT NULL COMMENT '服务器IP',
    cron_schedule VARCHAR(100) COMMENT 'cron表达式',
    command TEXT COMMENT '执行命令',
    execute_time VARCHAR(10) COMMENT '执行时间(HH:MM)',
    next_execute_time DATETIME COMMENT '下一次执行时间',
    last_execute_date DATE COMMENT '最后一次执行日期',
    last_execute_time DATETIME COMMENT '最后一次执行时间',
    status ENUM('success', 'failed', 'pending') DEFAULT 'pending' COMMENT '执行状态',
    exit_code INT COMMENT '退出码',
    error_message TEXT COMMENT '错误信息',
    log_content TEXT COMMENT '日志内容',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_job_name (job_name),
    INDEX idx_status (status),
    UNIQUE KEY unique_job (job_name, server_ip)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务监控表';
