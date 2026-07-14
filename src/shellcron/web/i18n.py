"""Simple i18n for Web UI templates."""

LANG_EN = "en"
LANG_ZH = "zh"

TRANSLATIONS = {
    "Tasks": {"zh": "任务"},
    "Logs": {"zh": "日志"},
    "Settings": {"zh": "设置"},
    "New Task": {"zh": "新建任务"},
    "Edit Task": {"zh": "编辑任务"},
    "Task Name": {"zh": "任务名称"},
    "Schedule Type": {"zh": "调度类型"},
    "Interval (days)": {"zh": "间隔（天）"},
    "Cron Expression": {"zh": "Cron 表达式"},
    "Time (HH:MM)": {"zh": "时间（HH:MM）"},
    "Scripts": {"zh": "脚本路径"},
    "Script Arguments": {"zh": "脚本参数"},
    "Misfire Policy": {"zh": "错过策略"},
    "Skip missed runs": {"zh": "跳过错过的执行"},
    "Catch up (run once)": {"zh": "补跑一次"},
    "Enable": {"zh": "启用"},
    "Disable": {"zh": "禁用"},
    "Enabled": {"zh": "已启用"},
    "Disabled": {"zh": "已禁用"},
    "Save": {"zh": "保存"},
    "Cancel": {"zh": "取消"},
    "Status": {"zh": "状态"},
    "Last Run": {"zh": "上次执行"},
    "Result": {"zh": "结果"},
    "Next Run": {"zh": "下次执行"},
    "Actions": {"zh": "操作"},
    "Edit": {"zh": "编辑"},
    "Run": {"zh": "运行"},
    "Delete": {"zh": "删除"},
    "Triggered": {"zh": "已触发"},
    "Running": {"zh": "运行中"},
    "Failed": {"zh": "失败"},
    "Success": {"zh": "成功"},
    "Waiting": {"zh": "等待中"},
    "No tasks.": {"zh": "暂无任务。"},
    "No tasks configured": {"zh": "暂无已配置的任务"},
    "Create one": {"zh": "创建任务"},
    "Execution Logs": {"zh": "执行日志"},
    "Filter": {"zh": "筛选"},
    "total": {"zh": "总计"},
    "enabled": {"zh": "已启用"},
    "running": {"zh": "运行中"},
    "failed": {"zh": "失败"},
    "All tasks": {"zh": "所有任务"},
    "No logs found.": {"zh": "暂无日志。"},
    "entries": {"zh": "条记录"},
    "Log Detail": {"zh": "日志详情"},
    "Script Results": {"zh": "脚本结果"},
    "Return code": {"zh": "返回码"},
    "Duration": {"zh": "耗时"},
    "Trigger": {"zh": "触发方式"},
    "Log Retention (days)": {"zh": "日志保留（天）"},
    "Default Shell": {"zh": "默认 Shell"},
    "Email Notifications": {"zh": "邮件通知"},
    "Enable email notifications": {"zh": "启用邮件通知"},
    "SMTP Server": {"zh": "SMTP 服务器"},
    "SMTP Port": {"zh": "SMTP 端口"},
    "SMTP Username": {"zh": "SMTP 用户名"},
    "SMTP Password": {"zh": "SMTP 密码"},
    "Recipient Email": {"zh": "收件邮箱"},
    "Save Settings": {"zh": "保存设置"},
    "Language": {"zh": "语言"},
    "English": {"zh": "English"},
    "中文": {"zh": "中文"},
    "Delete task": {"zh": "删除任务"},
    "No logs.": {"zh": "暂无日志。"},
    "Back": {"zh": "返回"},
    "Task": {"zh": "任务"},
    "Time": {"zh": "时间"},
    "Status": {"zh": "状态"},
    "Duration": {"zh": "耗时"},
    "truncated": {"zh": "已截断"},
    "Start time": {"zh": "开始时间"},
    "End time": {"zh": "结束时间"},
    "What to do when daemon was offline and a scheduled run was missed.": {
        "zh": "守护进程离线期间错过执行时的处理方式。"
    },
    "Format: minute hour day month weekday": {"zh": "格式：分钟 小时 日 月 星期"},
    "One per line": {"zh": "每行一个"},
    "Space-separated": {"zh": "空格分隔"},
}


def t(key: str, lang: str = "en") -> str:
    """Translate a key to the given language."""
    if lang == LANG_EN:
        return key
    entry = TRANSLATIONS.get(key)
    if entry and lang in entry:
        return entry[lang]
    return key
