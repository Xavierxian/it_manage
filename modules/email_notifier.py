import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
import os
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmailNotifier:
    def __init__(self):
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.qq.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_username = os.getenv('SMTP_USERNAME', '')
        self.smtp_password = os.getenv('SMTP_PASSWORD', '')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_username)
        self.from_name = os.getenv('FROM_NAME', 'IT运维管理平台')
        self.test_mode = os.getenv('EMAIL_TEST_MODE', 'true').lower() == 'true'
        self.test_email = os.getenv('TEST_EMAIL', 'xianxin@baison.com.cn')

    def send_email(self, to_emails, subject, content, is_html=False):
        try:
            if not to_emails:
                logger.warning('收件人列表为空，跳过发送邮件')
                return False, '收件人列表为空'

            msg = MIMEMultipart('alternative')
            # 使用formataddr函数正确格式化发件人，避免编码问题
            msg['From'] = formataddr((self.from_name, self.from_email))
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = Header(subject, 'utf-8')

            if is_html:
                msg.attach(MIMEText(content, 'html', 'utf-8'))
            else:
                msg.attach(MIMEText(content, 'plain', 'utf-8'))

            if self.smtp_port == 465:
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                    server.login(self.smtp_username, self.smtp_password)
                    server.sendmail(self.from_email, to_emails, msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.smtp_username, self.smtp_password)
                    server.sendmail(self.from_email, to_emails, msg.as_string())

            logger.info(f'邮件发送成功: {subject} -> {to_emails}')
            return True, '邮件发送成功'

        except smtplib.SMTPAuthenticationError:
            error_msg = 'SMTP认证失败，请检查用户名和密码'
            logger.error(error_msg)
            return False, error_msg
        except smtplib.SMTPException as e:
            error_msg = f'SMTP错误: {str(e)}'
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f'邮件发送失败: {str(e)}'
            logger.error(error_msg)
            return False, error_msg

    def send_host_alert_email(self, alert_data):
        try:
            to_email = alert_data.get('email')
            if not to_email:
                return False, '未找到对接人邮箱'

            ip = alert_data.get('ip', '未知')
            user = alert_data.get('user', '未知')
            department = alert_data.get('department', '未知')
            alerts = alert_data.get('alerts', [])

            subject = f'【告警通知】主机 {ip} 资源使用率告警'

            alert_items = ''
            for alert in alerts:
                alert_type = alert.get('type', '未知')
                value = alert.get('value', 0)
                threshold = alert.get('threshold', 80)
                alert_items += f'''
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{alert_type}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; color: #ef4444; font-weight: bold;">{value:.1f}%</td>
                    <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{threshold}%</td>
                </tr>
                '''

            html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>主机资源告警通知</title>
    <style>
        /* 基础样式重置 - 兼容Outlook */
        body, table, td, p, a, li, blockquote {{ 
            -webkit-text-size-adjust: 100%; 
            -ms-text-size-adjust: 100%; 
            margin: 0; 
            padding: 0; 
            border: 0; 
        }}
        
        /* 全局样式 */
        body {{ 
            font-family: Arial, sans-serif; 
            background-color: #f5f5f5; 
            color: #333; 
            line-height: 1.6; 
            font-size: 16px; /* 增大基础字体 */
        }}
        
        /* 邮件容器 - 使用传统表格布局兼容Outlook */
        .email-container {{ 
            max-width: 600px; 
            margin: 0 auto; 
            background: white; 
            border: 1px solid #ddd; 
        }}
        
        /* 头部样式 - 简化设计兼容Outlook */
        .header {{ 
            background-color: #dc3545; /* 纯色背景替代渐变 */
            color: white; 
            padding: 25px; 
            text-align: center; 
        }}
        .header h1 {{ 
            font-size: 24px; 
            font-weight: bold; 
            margin: 0; 
        }}
        .header .subtitle {{ 
            font-size: 16px; /* 增大字体 */
            margin-top: 8px; 
        }}
        
        /* 内容区域 */
        .content {{ 
            padding: 30px 25px; 
        }}
        
        /* 主机信息卡片 - 简化设计兼容Outlook */
        .host-info-card {{ 
            background-color: #e3f2fd; /* 纯色背景 */
            padding: 20px; 
            margin-bottom: 25px; 
            border: 1px solid #bbdefb; /* 边框替代渐变 */
        }}
        .host-info-item {{ 
            font-size: 16px; /* 增大字体 */
            margin: 12px 0; 
        }}
        .host-info-label {{ 
            font-weight: bold; 
            color: #1565c0; 
        }}
        .host-info-value {{ 
            color: #0d47a1; 
            font-weight: bold; 
        }}
        
        /* 标题样式 */
        .section-title {{ 
            font-size: 20px; /* 增大字体 */
            font-weight: bold; 
            color: #2d3436; 
            margin: 30px 0 18px 0; 
            padding-bottom: 12px; 
            border-bottom: 2px solid #dee2e6; 
        }}
        
        /* 表格样式 - 优化Outlook显示 */
        .alert-table {{ 
            width: 100%; 
            margin: 25px 0; 
            border-collapse: collapse; 
            font-size: 16px; /* 增大表格字体 */
        }}
        .alert-table th {{ 
            background-color: #f8f9fa; 
            color: #495057; 
            font-weight: bold; 
            text-align: left; 
            padding: 15px; 
            border: 1px solid #dee2e6; 
        }}
        .alert-table td {{ 
            padding: 15px; 
            border: 1px solid #dee2e6; 
            vertical-align: top; 
        }}
        
        /* 提示卡片 - 简化设计兼容Outlook */
        .info-card {{ 
            background-color: #d1ecf1; 
            padding: 20px; 
            margin: 25px 0; 
            border: 1px solid #bee5eb; /* 边框替代渐变 */
        }}
        .info-card .info-title {{ 
            font-weight: bold; 
            color: #0c5460; 
            margin-bottom: 10px; 
            font-size: 18px; /* 增大标题字体 */
        }}
        .info-card .info-content {{ 
            color: #055160; 
            line-height: 1.6; 
            font-size: 16px; /* 增大内容字体 */
        }}
        
        /* 告警值样式 */
        .alert-value {{ 
            color: #dc3545; 
            font-weight: bold; 
            font-size: 16px; /* 增大告警值字体 */
        }}
        
        /* 页脚样式 */
        .footer {{ 
            background-color: #f8f9fa; 
            padding: 20px; 
            text-align: center; 
            color: #6c757d; 
            font-size: 14px; 
            border-top: 1px solid #e9ecef; 
        }}
        
        /* 响应式设计 - 简化版本 */
        @media screen and (max-width: 600px) {{ 
            .email-container {{ 
                width: 100% !important; 
                margin: 10px !important; 
            }} 
            .header, .content, .footer {{ 
                padding: 15px !important; 
            }} 
            .alert-table, .alert-table th, .alert-table td {{ 
                font-size: 14px !important; 
                padding: 10px !important; 
            }} 
        }}
    </style>
</head>
<body>
    <table class="email-container" cellpadding="0" cellspacing="0" width="100%">
        <!-- 头部 -->
        <tr>
            <td class="header">
                <h1>⚠️ 主机资源告警通知</h1>
                <div class="subtitle">请及时处理，避免影响业务正常运行</div>
            </td>
        </tr>
        
        <!-- 内容 -->
        <tr>
            <td class="content">
                <!-- 主机信息卡片 -->
                <div class="host-info-card">
                    <div class="host-info-item">
                        <span class="host-info-label">主机IP：</span>
                        <span class="host-info-value">{ip}</span>
                    </div>
                    <div class="host-info-item">
                        <span class="host-info-label">对接人：</span>
                        <span class="host-info-value">{user}</span>
                    </div>
                    <div class="host-info-item">
                        <span class="host-info-label">所属部门：</span>
                        <span class="host-info-value">{department}</span>
                    </div>
                    <div class="host-info-item">
                        <span class="host-info-label">告警时间：</span>
                        <span class="host-info-value">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
                    </div>
                </div>
                
                <!-- 告警详情标题 -->
                <h2 class="section-title">告警详情</h2>
                
                <!-- 告警表格 -->
                <table class="alert-table">
                    <thead>
                        <tr>
                            <th>资源类型</th>
                            <th>当前值</th>
                            <th>告警阈值</th>
                        </tr>
                    </thead>
                    <tbody>
                        {alert_items}
                    </tbody>
                </table>
                
                <!-- 提示信息 -->
                <div class="info-card">
                    <div class="info-title">🔔 温馨提示</div>
                    <div class="info-content">
                        检测到您的服务器磁盘空间使用率已达到告警阈值，请及时进行磁盘清理操作，删除不必要的日志文件、临时文件或过期数据，必要时可联系信息中心进行扩容，避免影响业务正常运行。
                    </div>
                </div>
            </td>
        </tr>
        
        <!-- 页脚 -->
        <tr>
            <td class="footer">
                <p>此邮件由 IT运维管理平台 自动发送，请勿回复</p>
                <p>如有疑问，请联系信息中心</p>
            </td>
        </tr>
    </table>
</body>
</html>'''

            return self.send_email([to_email], subject, html_content, is_html=True)

        except Exception as e:
            logger.error(f'发送主机告警邮件失败: {str(e)}')
            return False, f'发送失败: {str(e)}'

    def send_batch_alert_emails(self, alerts_list):
        try:
            if not alerts_list:
                return {
                    'success': False,
                    'total': 0,
                    'success_count': 0,
                    'fail_count': 0,
                    'message': '没有告警数据'
                }

            to_email = alerts_list[0].get('email')
            if not to_email:
                return {
                    'success': False,
                    'total': len(alerts_list),
                    'success_count': 0,
                    'fail_count': len(alerts_list),
                    'message': '未找到对接人邮箱'
                }

            subject = f'【告警通知】主机资源告警汇总 - {len(alerts_list)}台主机'

            alert_rows = ''
            for alert_data in alerts_list:
                ip = alert_data.get('ip', '未知')
                user = alert_data.get('user', '未知')
                department = alert_data.get('department', '未知')
                alerts = alert_data.get('alerts', [])

                alert_details = ''
                for alert in alerts:
                    alert_type = alert.get('type', '未知')
                    value = alert.get('value', 0)
                    alert_details += f'<span class="alert-tag">{alert_type}: {value:.1f}%</span> '

                alert_rows += f'''
                <tr>
                    <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; font-weight: 600;">{ip}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{user}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{department}</td>
                    <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{alert_details}</td>
                </tr>
                '''

            html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>主机资源告警通知</title>
    <style>
        /* 基础样式重置 - 兼容Outlook */
        body, table, td, p, a, li, blockquote {{ 
            -webkit-text-size-adjust: 100%; 
            -ms-text-size-adjust: 100%; 
            margin: 0; 
            padding: 0; 
            border: 0; 
        }}
        
        /* 全局样式 */
        body {{ 
            font-family: Arial, sans-serif; 
            background-color: #f5f5f5; 
            color: #333; 
            line-height: 1.6; 
            font-size: 16px; /* 增大基础字体 */
        }}
        
        /* 邮件容器 - 使用传统表格布局兼容Outlook */
        .email-container {{ 
            max-width: 600px; 
            margin: 0 auto; 
            background: white; 
            border: 1px solid #ddd; 
        }}
        
        /* 头部样式 - 简化设计兼容Outlook */
        .header {{ 
            background-color: #dc3545; /* 纯色背景替代渐变 */
            color: white; 
            padding: 25px; 
            text-align: center; 
        }}
        .header h1 {{ 
            font-size: 24px; 
            font-weight: bold; 
            margin: 0; 
        }}
        .header .subtitle {{ 
            font-size: 16px; /* 增大字体 */
            margin-top: 8px; 
        }}
        
        /* 内容区域 */
        .content {{ 
            padding: 30px 25px; 
        }}
        
        /* 摘要卡片 - 简化设计兼容Outlook */
        .summary-card {{ 
            background-color: #fff3cd; /* 纯色背景 */
            padding: 20px; 
            margin-bottom: 25px; 
            border: 1px solid #ffeeba; /* 边框替代渐变 */
        }}
        .summary-item {{ 
            font-size: 16px; /* 增大字体 */
            margin: 12px 0; 
        }}
        .summary-label {{ 
            font-weight: bold; 
            color: #856404; 
        }}
        .summary-value {{ 
            color: #d84315; 
            font-weight: bold; 
        }}
        
        /* 标题样式 */
        .section-title {{ 
            font-size: 20px; /* 增大字体 */
            font-weight: bold; 
            color: #2d3436; 
            margin: 30px 0 18px 0; 
            padding-bottom: 12px; 
            border-bottom: 2px solid #dee2e6; 
        }}
        
        /* 表格样式 - 优化Outlook显示 */
        .alert-table {{ 
            width: 100%; 
            margin: 25px 0; 
            border-collapse: collapse; 
            font-size: 16px; /* 增大表格字体 */
        }}
        .alert-table th {{ 
            background-color: #f8f9fa; 
            color: #495057; 
            font-weight: bold; 
            text-align: left; 
            padding: 15px; 
            border: 1px solid #dee2e6; 
        }}
        .alert-table td {{ 
            padding: 15px; 
            border: 1px solid #dee2e6; 
            vertical-align: top; 
        }}
        
        /* 告警标签 - 简化设计兼容Outlook */
        .alert-tag {{ 
            display: inline-block; 
            background-color: #f8d7da; 
            color: #721c24; 
            padding: 8px 12px; /* 增大内边距 */
            margin: 4px 8px 4px 0; /* 增大外边距 */
            border-radius: 4px; 
            font-size: 14px; /* 增大标签字体 */
            border: 1px solid #f5c6cb; 
            font-weight: bold; 
        }}
        
        /* 提示卡片 - 简化设计兼容Outlook */
        .info-card {{ 
            background-color: #d1ecf1; 
            padding: 20px; 
            margin: 25px 0; 
            border: 1px solid #bee5eb; /* 边框替代渐变 */
        }}
        .info-card .info-title {{ 
            font-weight: bold; 
            color: #0c5460; 
            margin-bottom: 10px; 
            font-size: 18px; /* 增大标题字体 */
        }}
        .info-card .info-content {{ 
            color: #055160; 
            line-height: 1.6; 
            font-size: 16px; /* 增大内容字体 */
        }}
        
        /* 页脚样式 */
        .footer {{ 
            background-color: #f8f9fa; 
            padding: 20px; 
            text-align: center; 
            color: #6c757d; 
            font-size: 14px; 
            border-top: 1px solid #e9ecef; 
        }}
        
        /* 响应式设计 - 简化版本 */
        @media screen and (max-width: 600px) {{ 
            .email-container {{ 
                width: 100% !important; 
                margin: 10px !important; 
            }} 
            .header, .content, .footer {{ 
                padding: 15px !important; 
            }} 
            .alert-table, .alert-table th, .alert-table td {{ 
                font-size: 14px !important; 
                padding: 10px !important; 
            }} 
        }}
    </style>
</head>
<body>
    <table class="email-container" cellpadding="0" cellspacing="0" width="100%">
        <!-- 头部 -->
        <tr>
            <td class="header">
                <h1>⚠️ 主机资源告警通知</h1>
                <div class="subtitle">请及时处理，避免影响业务正常运行</div>
            </td>
        </tr>
        
        <!-- 内容 -->
        <tr>
            <td class="content">
                <!-- 摘要信息 -->
                <div class="summary-card">
                    <div class="summary-item">
                        <span class="summary-label">告警时间：</span>
                        <span class="summary-value">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
                    </div>
                    <div class="summary-item">
                        <span class="summary-label">告警主机数：</span>
                        <span class="summary-value">{len(alerts_list)} 台</span>
                    </div>
                </div>
                
                <!-- 告警详情标题 -->
                <h2 class="section-title">告警详情</h2>
                
                <!-- 告警表格 -->
                <table class="alert-table">
                    <thead>
                        <tr>
                            <th>主机IP</th>
                            <th>对接人</th>
                            <th>所属部门</th>
                            <th>告警类型</th>
                        </tr>
                    </thead>
                    <tbody>
                        {alert_rows}
                    </tbody>
                </table>
                
                <!-- 提示信息 -->
                <div class="info-card">
                    <div class="info-title">🔔 温馨提示</div>
                    <div class="info-content">
                        检测到您的服务器磁盘空间使用率已达到告警阈值，请及时进行磁盘清理操作，删除不必要的日志文件、临时文件或过期数据，必要时可联系信息中心进行扩容，避免影响业务正常运行。
                    </div>
                </div>
            </td>
        </tr>
        
        <!-- 页脚 -->
        <tr>
            <td class="footer">
                <p>此邮件由 IT运维管理平台 自动发送，请勿回复</p>
                <p>如有疑问，请联系信息中心</p>
            </td>
        </tr>
    </table>
</body>
</html>'''

            success, message = self.send_email([to_email], subject, html_content, is_html=True)

            return {
                'success': success,
                'total': len(alerts_list),
                'success_count': 1 if success else 0,
                'fail_count': 0 if success else 1,
                'message': message
            }

        except Exception as e:
            logger.error(f'发送批量告警邮件失败: {str(e)}')
            return {
                'success': False,
                'total': len(alerts_list),
                'success_count': 0,
                'fail_count': len(alerts_list),
                'message': f'发送失败: {str(e)}'
            }


    def send_alerts_by_user(self, alerts_list):
        try:
            if not alerts_list:
                return {
                    'success': False,
                    'total': 0,
                    'success_count': 0,
                    'fail_count': 0,
                    'message': '没有告警数据'
                }

            alerts_by_user = {}
            for alert in alerts_list:
                user = alert.get('user', '未知')
                if user not in alerts_by_user:
                    alerts_by_user[user] = []
                alerts_by_user[user].append(alert)

            success_count = 0
            fail_count = 0
            total_users = len(alerts_by_user)

            for user, user_alerts in alerts_by_user.items():
                to_email = user_alerts[0].get('email')
                if not to_email:
                    fail_count += 1
                    continue

                if self.test_mode and user != '鲜鑫':
                    to_email = self.test_email

                if user == '鲜鑫':
                    subject = f'【告警通知】主机资源告警汇总 - {len(alerts_list)}台主机'
                    alert_rows = ''
                    for alert_data in alerts_list:
                        ip = alert_data.get('ip', '未知')
                        user_name = alert_data.get('user', '未知')
                        department = alert_data.get('department', '未知')
                        alerts = alert_data.get('alerts', [])

                        alert_details = ''
                        for alert in alerts:
                            alert_type = alert.get('type', '未知')
                            value = alert.get('value', 0)
                            alert_details += f'<span class="alert-tag">{alert_type}: {value:.1f}%</span> '

                        alert_rows += f'''
                        <tr>
                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; font-weight: 600;">{ip}</td>
                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{user_name}</td>
                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{department}</td>
                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{alert_details}</td>
                        </tr>
                        '''
                else:
                    subject = f'【告警通知】您的主机资源告警 - {len(user_alerts)}台主机'
                    alert_rows = ''
                    for alert_data in user_alerts:
                        ip = alert_data.get('ip', '未知')
                        department = alert_data.get('department', '未知')
                        alerts = alert_data.get('alerts', [])

                        alert_details = ''
                        for alert in alerts:
                            alert_type = alert.get('type', '未知')
                            value = alert.get('value', 0)
                            alert_details += f'<span class="alert-tag">{alert_type}: {value:.1f}%</span> '

                        alert_rows += f'''
                        <tr>
                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; font-weight: 600;">{ip}</td>
                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{department}</td>
                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{alert_details}</td>
                        </tr>
                        '''

                html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>主机资源告警通知</title>
    <style>
        /* 基础样式重置 - 兼容Outlook */
        body, table, td, p, a, li, blockquote {{ 
            -webkit-text-size-adjust: 100%; 
            -ms-text-size-adjust: 100%; 
            margin: 0; 
            padding: 0; 
            border: 0; 
        }}
        
        /* 全局样式 */
        body {{ 
            font-family: Arial, sans-serif; 
            background-color: #f5f5f5; 
            color: #333; 
            line-height: 1.6; 
            font-size: 16px; /* 增大基础字体 */
        }}
        
        /* 邮件容器 - 使用传统表格布局兼容Outlook */
        .email-container {{ 
            max-width: 600px; 
            margin: 0 auto; 
            background: white; 
            border: 1px solid #ddd; 
        }}
        
        /* 头部样式 - 简化设计兼容Outlook */
        .header {{ 
            background-color: #dc3545; /* 纯色背景替代渐变 */
            color: white; 
            padding: 25px; 
            text-align: center; 
        }}
        .header h1 {{ 
            font-size: 24px; 
            font-weight: bold; 
            margin: 0; 
        }}
        .header .subtitle {{ 
            font-size: 16px; /* 增大字体 */
            margin-top: 8px; 
        }}
        
        /* 内容区域 */
        .content {{ 
            padding: 30px 25px; 
        }}
        
        /* 摘要卡片 - 简化设计兼容Outlook */
        .summary-card {{ 
            background-color: #fff3cd; /* 纯色背景 */
            padding: 20px; 
            margin-bottom: 25px; 
            border: 1px solid #ffeeba; /* 边框替代渐变 */
        }}
        .summary-item {{ 
            font-size: 16px; /* 增大字体 */
            margin: 12px 0; 
        }}
        .summary-label {{ 
            font-weight: bold; 
            color: #856404; 
        }}
        .summary-value {{ 
            color: #d84315; 
            font-weight: bold; 
        }}
        
        /* 标题样式 */
        .section-title {{ 
            font-size: 20px; /* 增大字体 */
            font-weight: bold; 
            color: #2d3436; 
            margin: 30px 0 18px 0; 
            padding-bottom: 12px; 
            border-bottom: 2px solid #dee2e6; 
        }}
        
        /* 表格样式 - 优化Outlook显示 */
        .alert-table {{ 
            width: 100%; 
            margin: 25px 0; 
            border-collapse: collapse; 
            font-size: 16px; /* 增大表格字体 */
        }}
        .alert-table th {{ 
            background-color: #f8f9fa; 
            color: #495057; 
            font-weight: bold; 
            text-align: left; 
            padding: 15px; 
            border: 1px solid #dee2e6; 
        }}
        .alert-table td {{ 
            padding: 15px; 
            border: 1px solid #dee2e6; 
            vertical-align: top; 
        }}
        
        /* 告警标签 - 简化设计兼容Outlook */
        .alert-tag {{ 
            display: inline-block; 
            background-color: #f8d7da; 
            color: #721c24; 
            padding: 8px 12px; /* 增大内边距 */
            margin: 4px 8px 4px 0; /* 增大外边距 */
            border-radius: 4px; 
            font-size: 14px; /* 增大标签字体 */
            border: 1px solid #f5c6cb; 
            font-weight: bold; 
        }}
        
        /* 提示卡片 - 简化设计兼容Outlook */
        .info-card {{ 
            background-color: #d1ecf1; 
            padding: 20px; 
            margin: 25px 0; 
            border: 1px solid #bee5eb; /* 边框替代渐变 */
        }}
        .info-card .info-title {{ 
            font-weight: bold; 
            color: #0c5460; 
            margin-bottom: 10px; 
            font-size: 18px; /* 增大标题字体 */
        }}
        .info-card .info-content {{ 
            color: #055160; 
            line-height: 1.6; 
            font-size: 16px; /* 增大内容字体 */
        }}
        
        /* 页脚样式 */
        .footer {{ 
            background-color: #f8f9fa; 
            padding: 20px; 
            text-align: center; 
            color: #6c757d; 
            font-size: 14px; 
            border-top: 1px solid #e9ecef; 
        }}
        
        /* 响应式设计 - 简化版本 */
        @media screen and (max-width: 600px) {{ 
            .email-container {{ 
                width: 100% !important; 
                margin: 10px !important; 
            }} 
            .header, .content, .footer {{ 
                padding: 15px !important; 
            }} 
            .alert-table, .alert-table th, .alert-table td {{ 
                font-size: 14px !important; 
                padding: 10px !important; 
            }} 
        }}
    </style>
</head>
<body>
    <table class="email-container" cellpadding="0" cellspacing="0" width="100%">
        <!-- 头部 -->
        <tr>
            <td class="header">
                <h1>⚠️ 主机资源告警通知</h1>
                <div class="subtitle">请及时处理，避免影响业务正常运行</div>
            </td>
        </tr>
        
        <!-- 内容 -->
        <tr>
            <td class="content">
                <!-- 摘要信息 -->
                <div class="summary-card">
                    <div class="summary-item">
                        <span class="summary-label">告警时间：</span>
                        <span class="summary-value">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
                    </div>
                    <div class="summary-item">
                        <span class="summary-label">告警主机数：</span>
                        <span class="summary-value">{len(user_alerts if user != '鲜鑫' else alerts_list)} 台</span>
                    </div>
                </div>
                
                <!-- 告警详情标题 -->
                <h2 class="section-title">告警详情</h2>
                
                <!-- 告警表格 -->
                <table class="alert-table">
                    <thead>
                        <tr>
                            <th>主机IP</th>
                            {'' if user != '鲜鑫' else '<th>对接人</th>'}
                            <th>所属部门</th>
                            <th>告警类型</th>
                        </tr>
                    </thead>
                    <tbody>
                        {alert_rows}
                    </tbody>
                </table>
                
                <!-- 提示信息 -->
                <div class="info-card">
                    <div class="info-title">🔔 温馨提示</div>
                    <div class="info-content">
                        检测到您的服务器磁盘空间使用率已达到告警阈值，请及时进行磁盘清理操作，删除不必要的日志文件、临时文件或过期数据，必要时可联系信息中心进行扩容，避免影响业务正常运行。
                    </div>
                </div>
            </td>
        </tr>
        
        <!-- 页脚 -->
        <tr>
            <td class="footer">
                <p>此邮件由 IT运维管理平台 自动发送，请勿回复</p>
                <p>如有疑问，请联系信息中心</p>
            </td>
        </tr>
    </table>
</body>
</html>'''

                success, message = self.send_email([to_email], subject, html_content, is_html=True)
                if success:
                    success_count += 1
                else:
                    fail_count += 1

            return {
                'success': success_count > 0,
                'total': total_users,
                'success_count': success_count,
                'fail_count': fail_count,
                'message': f'成功发送 {success_count} 封邮件，失败 {fail_count} 封'
            }

        except Exception as e:
            logger.error(f'按使用人发送告警邮件失败: {str(e)}')
            return {
                'success': False,
                'total': len(alerts_list),
                'success_count': 0,
                'fail_count': len(alerts_list),
                'message': f'发送失败: {str(e)}'
            }


email_notifier = EmailNotifier()
