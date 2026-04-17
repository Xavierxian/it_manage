from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from .auth import permission_required
from .database import get_db_connection

qualification_management_bp = Blueprint('qualification_management', __name__)

ACTIVE_STATUS_VALUES = {
    'active',
    'valid',
    'enabled',
    'effective',
    'in_use',
    '有效',
    '正常',
    '启用',
    '使用中',
    '生效中',
}

SEARCH_FIELDS = (
    'qualification_category',
    'belong_entity',
    'belong_department',
    'qualification_name',
    'manager',
    'usage',
    'cost',
    'account',
    'status',
    'remark',
    'supplier_name',
)


def _normalize_text(value):
    return str(value or '').strip()


def _status_key(value):
    return _normalize_text(value).lower()


def _format_decimal_text(value):
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return _normalize_text(value)

    text = f"{decimal_value:.2f}"
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text


def _parse_datetime_input(value):
    text = _normalize_text(value)
    if not text:
        return None

    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == '%Y-%m-%d':
                return datetime.combine(parsed.date(), datetime.min.time())
            return parsed
        except ValueError:
            continue

    raise ValueError('到期日期格式不正确')


def _serialize_purchase_detail(row):
    expire_date = row.get('expire_date')
    create_time = row.get('create_time')

    return {
        'id': row.get('id'),
        'parent_id': row.get('parent_id'),
        'create_time': create_time.strftime('%Y-%m-%d %H:%M:%S') if create_time else '',
        'cost_amount': _format_decimal_text(row.get('cost_amount')),
        'expire_date': expire_date.strftime('%Y-%m-%d %H:%M:%S') if expire_date else '',
        'remark': _normalize_text(row.get('remark')),
    }


def _load_purchase_aggregates(connection):
    aggregates = {}
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                parent_id,
                COUNT(*) AS purchase_count,
                MAX(create_time) AS latest_purchase_time
            FROM purchase_detail
            GROUP BY parent_id
            """
        )
        for row in cursor.fetchall():
            aggregates[row['parent_id']] = row
    return aggregates


def _serialize_qualification(row, aggregate=None):
    today = date.today()
    expire_date = row.get('expire_date')
    password_value = _normalize_text(row.get('password'))
    days_to_expire = None

    expiry_state = 'unknown'
    if expire_date:
        days_to_expire = (expire_date - today).days
        if expire_date < today:
            expiry_state = 'expired'
        elif expire_date <= today + timedelta(days=30):
            expiry_state = 'expiring_soon'
        else:
            expiry_state = 'valid'

    purchase_count = 0
    latest_purchase_time = ''
    if aggregate:
        purchase_count = aggregate.get('purchase_count') or 0
        latest_time = aggregate.get('latest_purchase_time')
        if latest_time:
            latest_purchase_time = latest_time.strftime('%Y-%m-%d %H:%M:%S')

    return {
        'id': row.get('id'),
        'qualification_category': _normalize_text(row.get('qualification_category')),
        'belong_entity': _normalize_text(row.get('belong_entity')),
        'belong_department': _normalize_text(row.get('belong_department')),
        'qualification_name': _normalize_text(row.get('qualification_name')),
        'manager': _normalize_text(row.get('manager')),
        'usage': _normalize_text(row.get('usage')),
        'cost': _normalize_text(row.get('cost')),
        'account': _normalize_text(row.get('account')),
        'password_masked': '*' * min(max(len(password_value), 6), 12) if password_value else '',
        'has_password': bool(password_value),
        'status': _normalize_text(row.get('status')),
        'expire_date': expire_date.strftime('%Y-%m-%d') if expire_date else '',
        'remark': _normalize_text(row.get('remark')),
        'supplier_name': _normalize_text(row.get('supplier_name')),
        'last_update_time': row.get('last_update_time').strftime('%Y-%m-%d %H:%M:%S')
        if row.get('last_update_time')
        else '',
        'create_time': row.get('create_time').strftime('%Y-%m-%d %H:%M:%S')
        if row.get('create_time')
        else '',
        'expiry_state': expiry_state,
        'days_to_expire': days_to_expire,
        'purchase_count': purchase_count,
        'latest_purchase_time': latest_purchase_time,
    }


def _build_stats(rows):
    today = date.today()
    total = len(rows)
    active = 0
    expired = 0
    expiring_soon = 0
    categories = set()

    for row in rows:
        category = _normalize_text(row.get('qualification_category'))
        if category:
            categories.add(category)

        if _status_key(row.get('status')) in ACTIVE_STATUS_VALUES:
            active += 1

        expire_date = row.get('expire_date')
        if expire_date:
            if expire_date < today:
                expired += 1
            elif expire_date <= today + timedelta(days=30):
                expiring_soon += 1

    return {
        'total': total,
        'active': active,
        'expired': expired,
        'expiring_soon': expiring_soon,
        'categories': len(categories),
    }


def _build_filter_options(rows):
    def distinct_values(field_name):
        values = {_normalize_text(row.get(field_name)) for row in rows}
        values.discard('')
        return sorted(values)

    return {
        'categories': distinct_values('qualification_category'),
        'departments': distinct_values('belong_department'),
        'statuses': distinct_values('status'),
    }


def _matches_search(row, search_term):
    if not search_term:
        return True

    haystack = ' '.join(_normalize_text(row.get(field)) for field in SEARCH_FIELDS).lower()
    return search_term in haystack


def _matches_filter(row, category, department, status, expiry_state):
    if category and _normalize_text(row.get('qualification_category')) != category:
        return False

    if department and _normalize_text(row.get('belong_department')) != department:
        return False

    if status and _normalize_text(row.get('status')) != status:
        return False

    if expiry_state:
        serialized = _serialize_qualification(row)
        if serialized['expiry_state'] != expiry_state:
            return False

    return True


def _load_qualifications(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM qualification_management
            ORDER BY expire_date IS NULL, expire_date ASC, id DESC
            """
        )
        return cursor.fetchall()


def _load_single_qualification(connection, qualification_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM qualification_management
            WHERE id = %s
            """,
            (qualification_id,),
        )
        return cursor.fetchone()


def _load_purchase_details(connection, qualification_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, parent_id, create_time, cost_amount, expire_date, remark
            FROM purchase_detail
            WHERE parent_id = %s
            ORDER BY create_time DESC, id DESC
            """,
            (qualification_id,),
        )
        return cursor.fetchall()


@qualification_management_bp.route('/qualification_management')
@login_required
@permission_required('qualification_management')
def qualification_management():
    return render_template('qualification_management.html')


@qualification_management_bp.route('/api/qualifications')
@login_required
@permission_required('qualification_management')
def get_qualifications():
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'message': '数据库连接失败'}), 500

    try:
        rows = _load_qualifications(connection)
        aggregates = _load_purchase_aggregates(connection)

        search = _normalize_text(request.args.get('search')).lower()
        category = _normalize_text(request.args.get('category'))
        department = _normalize_text(request.args.get('department'))
        status = _normalize_text(request.args.get('status'))
        expiry_state = _normalize_text(request.args.get('expiry_state'))

        filtered_rows = [
            row
            for row in rows
            if _matches_search(row, search)
            and _matches_filter(row, category, department, status, expiry_state)
        ]

        return jsonify(
            {
                'success': True,
                'qualifications': [
                    _serialize_qualification(row, aggregates.get(row.get('id')))
                    for row in filtered_rows
                ],
                'stats': _build_stats(rows),
                'total': len(rows),
                'filtered_total': len(filtered_rows),
                'filter_options': _build_filter_options(rows),
            }
        )
    except Exception as exc:
        import traceback

        traceback.print_exc()
        return jsonify(
            {
                'success': False,
                'message': f'获取资质数据失败: {exc}',
                'qualifications': [],
                'stats': {
                    'total': 0,
                    'active': 0,
                    'expired': 0,
                    'expiring_soon': 0,
                    'categories': 0,
                },
                'total': 0,
                'filtered_total': 0,
                'filter_options': {
                    'categories': [],
                    'departments': [],
                    'statuses': [],
                },
            }
        ), 500
    finally:
        connection.close()


@qualification_management_bp.route('/api/qualifications/<int:qualification_id>/purchase-details')
@login_required
@permission_required('qualification_management')
def get_purchase_details(qualification_id):
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'message': '数据库连接失败'}), 500

    try:
        qualification = _load_single_qualification(connection, qualification_id)
        if not qualification:
            return jsonify({'success': False, 'message': '资质不存在'}), 404

        aggregates = _load_purchase_aggregates(connection)
        details = _load_purchase_details(connection, qualification_id)

        return jsonify(
            {
                'success': True,
                'qualification': _serialize_qualification(
                    qualification,
                    aggregates.get(qualification_id),
                ),
                'details': [_serialize_purchase_detail(row) for row in details],
            }
        )
    except Exception as exc:
        import traceback

        traceback.print_exc()
        return jsonify({'success': False, 'message': f'获取明细失败: {exc}', 'details': []}), 500
    finally:
        connection.close()


@qualification_management_bp.route('/api/qualifications/<int:qualification_id>/purchase-details', methods=['POST'])
@login_required
@permission_required('qualification_management')
def add_purchase_detail(qualification_id):
    data = request.get_json(silent=True) or {}

    try:
        cost_amount = Decimal(str(data.get('cost_amount', '')).strip())
        if cost_amount < 0:
            raise ValueError('续费金额不能小于 0')
    except (InvalidOperation, ValueError):
        return jsonify({'success': False, 'message': '请输入正确的续费金额'}), 400

    try:
        expire_datetime = _parse_datetime_input(data.get('expire_date'))
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400

    if not expire_datetime:
        return jsonify({'success': False, 'message': '请选择到期日期'}), 400

    remark = _normalize_text(data.get('remark'))

    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'message': '数据库连接失败'}), 500

    try:
        qualification = _load_single_qualification(connection, qualification_id)
        if not qualification:
            return jsonify({'success': False, 'message': '资质不存在'}), 404

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO purchase_detail (parent_id, cost_amount, expire_date, remark)
                VALUES (%s, %s, %s, %s)
                """,
                (qualification_id, cost_amount, expire_datetime, remark or None),
            )

            cursor.execute(
                """
                UPDATE qualification_management
                SET cost = %s,
                    expire_date = %s,
                    remark = COALESCE(NULLIF(%s, ''), remark),
                    last_update_time = NOW()
                WHERE id = %s
                """,
                (
                    _format_decimal_text(cost_amount),
                    expire_datetime.date(),
                    remark,
                    qualification_id,
                ),
            )

        connection.commit()
        return jsonify({'success': True, 'message': '续费记录添加成功'})
    except Exception as exc:
        connection.rollback()
        import traceback

        traceback.print_exc()
        return jsonify({'success': False, 'message': f'添加续费记录失败: {exc}'}), 500
    finally:
        connection.close()
