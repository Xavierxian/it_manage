from flask import Blueprint, render_template, request, redirect, jsonify, send_file
from flask_login import login_required
from functools import wraps
import requests
import time
import pandas as pd
from io import BytesIO
from cachetools import TTLCache
from .database import get_db_connection
from .auth import permission_required
import os
from dotenv import load_dotenv

load_dotenv()

jumpserver_bp = Blueprint('jumpserver', __name__)

apiEndpoint = "https://jump.baison.net/api/openapi"

token = None
token_expiration_time = 0

credentials_cache = {}
hosts_cache = TTLCache(maxsize=1000, ttl=3600)

cache_timeout = 3600

cache_expiration_time = {}


def get_token():
    global token, token_expiration_time

    token_url = "/oauth"
    access_key_id = os.getenv('JUMPSERVER_ACCESS_KEY_ID')
    access_key_secret = os.getenv('JUMPSERVER_ACCESS_KEY_SECRET')
    
    if not access_key_id or not access_key_secret:
        print("JumpServer API credentials not found in environment variables")
        return None
    params = {
        "accessKeyId": access_key_id,
        "accessKeySecret": access_key_secret,
        "expireSeconds": 3600
    }

    response = requests.get(apiEndpoint + token_url, params=params)

    if response.status_code == 200:
        token = response.json().get("token")
        token_expiration_time = time.time() + 3600
        return token
    else:
        print("Failed to get token:", response.text)
        return None


def is_token_expired():
    return time.time() >= token_expiration_time


def refresh_token_if_needed():
    global token
    if is_token_expired():
        print("Token expired, refreshing...")
        token = get_token()


def is_cache_expired(host_id):
    return time.time() >= cache_expiration_time.get(host_id, 0)


def set_credentials(host_id, credentials):
    credentials_cache[host_id] = credentials
    cache_expiration_time[host_id] = time.time() + cache_timeout


@jumpserver_bp.route('/bastionManagement')
@login_required
@permission_required('bastion_management')
def bastionManagement():
    refresh_token_if_needed()
    remaining_time = max(0, token_expiration_time - time.time())

    online_count_data = count_online()
    online_count = online_count_data.get('count', 0) if isinstance(online_count_data, dict) else 0

    return render_template('baoleiji.html', token=token, remaining_time=int(remaining_time), online_count=online_count)


@jumpserver_bp.route('/get_hosts', methods=['GET'])
def get_hosts():
    refresh_token_if_needed()
    if token:
        if 'hosts' in hosts_cache:
            print("Returning cached hosts information.")
            return jsonify(hosts_cache['hosts'])

        params = {
            "page": 1,
            "size": 100000
        }
        headers = {
            "Accept": "application/json",
            "Authorization": token
        }

        response = requests.get(apiEndpoint + "/host/byCloud/49149403766784", params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()
            hosts_info = [
                {
                    "hostName": host.get("hostName"),
                    "operatingSystem": host.get("operatingSystem"),
                    "description": host.get("description"),
                    "hostId": str(host.get("hostId"))
                }
                for host in data.get("hosts", [])
            ]

            hosts_cache['hosts'] = hosts_info

            return jsonify(hosts_info)
        else:
            return jsonify({"error": response.text}), response.status_code
    return jsonify({"error": "Token is invalid"}), 403


@jumpserver_bp.route('/get_credentials/<host_id>', methods=['GET'])
def get_credentials(host_id):
    refresh_token_if_needed()
    if token:
        if host_id in credentials_cache:
            print(f"Returning cached credentials for host {host_id}")
            return jsonify(credentials_cache[host_id])

        url = f"https://jump.baison.net/api/openapi/credential/byHost/{host_id}?isPasswordProvide=false&encryptSensitive=false"
        headers = {
            "Accept": "application/json",
            "Authorization": token
        }

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            credentials_info = response.json()

            credentials_cache[host_id] = credentials_info

            return jsonify(credentials_info)
        else:
            return jsonify({"error": response.text}), response.status_code
    return jsonify({"error": "Token is invalid"}), 403


@jumpserver_bp.route('/export_hosts', methods=['GET'])
def export_hosts():
    refresh_token_if_needed()
    if token:
        params = {
            "page": 1,
            "size": 100000
        }
        headers = {
            "Accept": "application/json",
            "Authorization": token
        }

        response = requests.get(apiEndpoint + "/host/byCloud/49149403766784", params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()
            hosts_info = [
                {
                    "hostName": host.get("hostName"),
                    "operatingSystem": host.get("operatingSystem"),
                    "description": host.get("description"),
                    "hostId": str(host.get("hostId"))
                }
                for host in data.get("hosts", [])
            ]

            df = pd.DataFrame(hosts_info)

            df['hostId'] = df['hostId'].astype(str)

            output = BytesIO()
            df.to_excel(output, index=False)
            output.seek(0)

            return send_file(output, as_attachment=True, download_name='在用堡垒机主机清单.xlsx',
                             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        else:
            return jsonify({"error": response.text}), response.status_code
    return jsonify({"error": "Token is invalid"}), 403


@jumpserver_bp.route('/oauth_login', methods=['GET'])
def oauth_login():
    refresh_token_if_needed()
    if token:
        url = "https://jump.baison.net/api/openapi/oauthLogin"
        params = {
            "userId": "168692671705088",
            "oneoff": "false",
            "expireSeconds": 600,
            "teamId": 1,
            "page": "Home"
        }
        headers = {
            "Accept": "application/json",
            "Authorization": token
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            redirect_url = response.json().get("url")
            return redirect(redirect_url)
        else:
            return jsonify({"error": response.text}), response.status_code
    return jsonify({"error": "Token is invalid"}), 403


@jumpserver_bp.route('/delete_host/<host_id>', methods=['DELETE'])
def delete_host(host_id):
    refresh_token_if_needed()
    if token:
        url = f"https://jump.baison.net/api/openapi/host/{host_id}"
        headers = {
            "Accept": "application/json",
            "Authorization": token
        }

        response = requests.delete(url, headers=headers)

        if response.status_code == 204:
            return jsonify({"message": "Host deleted successfully."}), 204
        else:
            return jsonify({"error": response.text}), response.status_code
    return jsonify({"error": "Token is invalid"}), 403


@jumpserver_bp.route('/count_online')
def count_online():
    refresh_token_if_needed()
    if token:
        url = 'https://jump.baison.net/api/openapi/users/countOnline'
        headers = {
            'Accept': 'application/json',
            'Authorization': token
        }

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            online_count = data.get('count', 0)
            print(f"在线人数: {online_count}")
            return {"count": online_count}
        else:
            print(f"获取在线人数失败: {response.text}")
            return {"error": response.text}
    return {"error": "Token is invalid"}


@jumpserver_bp.route('/get_user_info/<account>', methods=['GET'])
def get_user_info(account):
    refresh_token_if_needed()
    if token:
        url = f"{apiEndpoint}/user/byAccount/{account}"
        headers = {
            "Accept": "application/json",
            "Authorization": token
        }

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            user_info = response.json()
            return jsonify(user_info)
        else:
            return jsonify({"error": response.text}), response.status_code
    return jsonify({"error": "Token is invalid"}), 403


@jumpserver_bp.route('/restart_host/<host_id>', methods=['POST'])
def restart_host(host_id):
    refresh_token_if_needed()
    if token:
        url = f"https://jump.baison.net/api/openapi/host/{host_id}/restart?force=true"
        headers = {
            "Accept": "application/json",
            "Authorization": token
        }

        response = requests.post(url, headers=headers)

        if response.status_code == 204:
            return jsonify({"message": "虚拟机重启请求成功。"}), 204
        else:
            return jsonify({"error": response.text}), response.status_code
    return jsonify({"error": "Token is invalid"}), 403


@jumpserver_bp.route('/modify_credential_password', methods=['POST'])
def modify_credential_password():
    refresh_token_if_needed()

    data = request.get_json()
    credential_id = data.get('credentialId')
    new_password = data.get('password')

    if not credential_id or not new_password:
        return jsonify({"error": "Missing credentialId or password"}), 400

    url = f"{apiEndpoint}/credential/modifyCredentialPass?credentialIds={credential_id}&password={new_password}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": token
    }

    response = requests.post(url, headers=headers)

    if response.status_code == 200:
        return jsonify({"message": "Password updated successfully"}), 200
    else:
        return jsonify({"error": response.text}), response.status_code


@jumpserver_bp.route('/ping', methods=['GET'])
def ping():
    refresh_token_if_needed()

    if token:
        url = "https://jump.baison.net/api/openapi/ping"
        headers = {
            "Accept": "application/json",
            "Authorization": token
        }

        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                return jsonify(response.json()), 200
            else:
                return jsonify({"error": response.text, "status": "failure"}), response.status_code

        except requests.exceptions.RequestException as e:
            return jsonify({"error": str(e), "status": "failure"}), 500

    return jsonify({"error": "Token is invalid", "status": "failure"}), 403


@jumpserver_bp.route('/add_user_auth', methods=['POST'])
def add_user_auth():
    refresh_token_if_needed()

    data = request.get_json()
    host_id = data.get('hostId')
    user_id = data.get('userId')

    if not host_id or not user_id:
        return jsonify({"error": "Missing hostId or userId"}), 400

    url = f"https://jump.baison.net/api/openapi/hostUserAuth/{host_id}?userId={user_id}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": token
    }

    try:
        response = requests.post(url, headers=headers)

        if response.status_code == 200:
            return jsonify({"message": "User authorized successfully"}), 200
        else:
            return jsonify({"error": response.text, "status": "failure"}), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e), "status": "failure"}), 500


@jumpserver_bp.route('/baoleiji_new')
def baoleiji_new():
    refresh_token_if_needed()
    online_count_data = count_online()
    online_count = online_count_data.get('count', 0) if isinstance(online_count_data, dict) else 0
    return render_template('baoleiji_modern.html', online_count=online_count)
