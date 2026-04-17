import pymysql
import json
from dotenv import load_dotenv
import os

load_dotenv()

def update_user_permissions():
    try:
        connection = pymysql.connect(
            host=os.getenv('MYSQL_HOST'),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DATABASE'),
            port=int(os.getenv('MYSQL_PORT', 3306)),
            cursorclass=pymysql.cursors.DictCursor
        )
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, username, role, permissions FROM users WHERE username = 'xianxin'")
            user = cursor.fetchone()
            
            if user:
                print(f"当前用户: {user['username']}")
                print(f"当前角色: {user['role']}")
                print(f"当前权限: {user['permissions']}")
                
                permissions = json.loads(user['permissions'])
                print(f"解析后的权限: {permissions}")
                
                if 'cron_monitoring' not in permissions:
                    permissions.append('cron_monitoring')
                    new_permissions = json.dumps(permissions)
                    
                    cursor.execute(
                        "UPDATE users SET permissions = %s WHERE id = %s",
                        (new_permissions, user['id'])
                    )
                    connection.commit()
                    
                    print(f"\n✓ 已成功添加 cron_monitoring 权限")
                    print(f"新权限列表: {permissions}")
                else:
                    print(f"\n✓ 用户已有 cron_monitoring 权限")
            else:
                print("未找到用户 xianxin")
        
        connection.close()
        
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    update_user_permissions()
