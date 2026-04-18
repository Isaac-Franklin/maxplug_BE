# marketplace/helpers.py

import uuid
import requests
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from .models import (
    Product, ProductMedia, ProductReceipt, ProductVariant,
    SellerWallet, WalletTransaction, EscrowEntry, Order, OrderItem,
    SellerProfile, Notification, Category,
)


# ─────────────────────────────────────────────────────────────────────
# RESPONSE HELPERS
# ─────────────────────────────────────────────────────────────────────

def success_response(data=None, message='Success', status=200, **kwargs):
    """Standard success envelope used across all views."""
    from rest_framework.response import Response
    payload = {'success': True, 'message': message}
    if data is not None:
        payload['data'] = data
    payload.update(kwargs)
    return Response(payload, status=status)


def error_response(message='An error occurred', status=400, errors=None):
    """Standard error envelope."""
    from rest_framework.response import Response
    payload = {'success': False, 'message': message}
    if errors:
        payload['errors'] = errors
    return Response(payload, status=status)


def paginate_queryset(queryset, request, serializer_class, page_size=20):
    """
    Simple manual pagination helper.
    Returns {results, count, next, previous} dict.
    """
    from django.core.paginator import Paginator, EmptyPage
    page = int(request.query_params.get('page', 1))
    size = int(request.query_params.get('page_size', page_size))
    paginator = Paginator(queryset, size)
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        return {'results': [], 'count': paginator.count, 'next': None, 'previous': None}

    data = serializer_class(page_obj.object_list, many=True, context={'request': request}).data

    def build_url(p):
        req = request.build_absolute_uri(request.path)
        params = request.query_params.copy()
        params['page'] = p
        return req + '?' + params.urlencode()

    return {
        'results': data,
        'count': paginator.count,
        'next': build_url(page + 1) if page_obj.has_next() else None,
        'previous': build_url(page - 1) if page_obj.has_previous() else None,
    }


# ─────────────────────────────────────────────────────────────────────
# PRODUCT HELPERS
# ─────────────────────────────────────────────────────────────────────

def resolve_category(name):
    """Find a Category by name (case-insensitive). Returns None if not found."""
    if not name:
        return None
    return Category.objects.filter(name__iexact=name).first()


def build_delivery_method_label(delivery: dict) -> str:
    """
    Derive the delivery_method field value from the Flutter delivery payload.
    """
    buyers_pickup = delivery.get('buyers_pickup', False)
    secondary = delivery.get('secondary_delivery')

    if buyers_pickup and secondary:
        return 'combined'
    if buyers_pickup:
        return 'buyers_pickup'
    if secondary == 'sellers_delivery':
        return 'sellers_delivery'
    if secondary == 'yangaplug_delivery':
        return 'yangaplug_delivery'
    return 'sellers_delivery'


@transaction.atomic
def create_product_from_payload(seller, validated_data, media_files, receipt_files):
    """
    Core logic to create a Product + media + receipts + variants from the
    Flutter CreateProductSerializer validated payload.
    Used by both the seller listing view and the admin publish view.
    """
    delivery = validated_data.get('delivery', {})
    condition_map = {'Brand New': 'new', 'Used': 'used', 'Both': 'both', 'new': 'new', 'used': 'used', 'both': 'both'}

    # ── Resolve category ─────────────────────────────────────────────
    category = resolve_category(validated_data.get('category'))
    subcategory = resolve_category(validated_data.get('subcategory'))

    # ── Get seller commission rate ────────────────────────────────────
    commission_rate = Decimal(str(seller.commission_rate)) if seller else Decimal('0.0500')

    product = Product.objects.create(
        seller=seller,
        name=validated_data['name'],
        description=validated_data.get('description', ''),
        category=category,
        subcategory=subcategory,
        item_type=validated_data.get('item_type', 'simple'),
        condition=condition_map.get(validated_data.get('condition', 'new'), 'new'),
        weight_kg=validated_data.get('weight_kg'),
        stock_count=validated_data.get('quantity', 0),
        seller_price=Decimal(str(validated_data['seller_price'])),
        commission_rate=commission_rate,
        delivery_method=build_delivery_method_label(delivery),
        delivery_days=delivery.get('delivery_timeline'),
        dispatch_state=delivery.get('dispatch_state'),
        pickup_address=delivery.get('pickup_address'),
        state_lga_delivery_options=(
            delivery.get('state_lga_options', []) +
            delivery.get('location_delivery_options', [])
        ),
        status='pending',
        source='seller',
    )

    # ── Media files ──────────────────────────────────────────────────
    for idx, f in enumerate(media_files):
        ext = f.name.rsplit('.', 1)[-1].lower()
        media_type = 'video' if ext in ('mp4', 'mov', 'avi') else 'image'
        ProductMedia.objects.create(
            product=product,
            file=f,
            media_type=media_type,
            is_primary=(idx == 0),
            order=idx,
        )

    # ── Receipt files (optional) ─────────────────────────────────────
    for f in receipt_files:
        ProductReceipt.objects.create(product=product, file=f)

    return product


# ─────────────────────────────────────────────────────────────────────
# WALLET HELPERS
# ─────────────────────────────────────────────────────────────────────

def get_or_create_wallet(seller):
    """Return the SellerWallet for a seller, creating one if absent."""
    wallet, _ = SellerWallet.objects.get_or_create(seller=seller)
    return wallet


def credit_wallet(seller, amount, category, description, reference_id=None):
    """Add funds to a seller's available balance and log the transaction."""
    wallet = get_or_create_wallet(seller)
    wallet.available_balance += Decimal(str(amount))
    wallet.total_earned += Decimal(str(amount))
    wallet.save(update_fields=['available_balance', 'total_earned'])
    WalletTransaction.objects.create(
        wallet=wallet,
        transaction_type='credit',
        category=category,
        amount=amount,
        description=description,
        reference_id=reference_id,
        status='completed',
    )
    return wallet


def debit_wallet(seller, amount, category, description, reference_id=None):
    """Deduct funds from a seller's available balance and log the transaction."""
    wallet = get_or_create_wallet(seller)
    if wallet.available_balance < Decimal(str(amount)):
        raise ValueError('Insufficient balance')
    wallet.available_balance -= Decimal(str(amount))
    wallet.total_withdrawn += Decimal(str(amount))
    wallet.save(update_fields=['available_balance', 'total_withdrawn'])
    WalletTransaction.objects.create(
        wallet=wallet,
        transaction_type='debit',
        category=category,
        amount=amount,
        description=description,
        reference_id=reference_id,
        status='completed',
    )
    return wallet


def hold_in_escrow(seller, order, order_item, amount):
    """Move seller earnings into escrow at order creation."""
    wallet = get_or_create_wallet(seller)
    wallet.escrow_balance += Decimal(str(amount))
    wallet.save(update_fields=['escrow_balance'])
    escrow = EscrowEntry.objects.create(
        seller=seller,
        order=order,
        order_item=order_item,
        amount=amount,
        status='holding',
    )
    WalletTransaction.objects.create(
        wallet=wallet,
        transaction_type='credit',
        category='sale',
        amount=amount,
        description=f'Sale earnings held in escrow — Order #{order.order_number}',
        reference_id=str(order.id),
        status='completed',
    )
    return escrow


# ─────────────────────────────────────────────────────────────────────
# EXTERNAL WALLET SYNC
# ─────────────────────────────────────────────────────────────────────

PHP_BACKEND_URL = 'https://your-php-backend.com/api'   # TODO: move to settings.py
PHP_BACKEND_API_KEY = 'YOUR_PHP_BACKEND_SECRET'         # TODO: move to settings.py / env


def sync_external_balance(user, auth_token=None):
    """
    Fetch this user's balance from the PHP backend and mirror it on our wallet.
    auth_token is the user's token forwarded from the Flutter app.

    Expected PHP response:
        { "status": "success", "balance": 50000.00, "currency": "NGN" }
    """
    from .models import ExternalBalanceSyncLog

    seller = getattr(user, 'seller_profile', None)
    if not seller:
        return None

    wallet = get_or_create_wallet(seller)
    headers = {}
    if auth_token:
        headers['Authorization'] = f'Bearer {auth_token}'
    headers['X-Api-Key'] = PHP_BACKEND_API_KEY

    try:
        resp = requests.get(
            f'{PHP_BACKEND_URL}/wallet/balance',
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        balance = Decimal(str(data.get('balance', 0)))

        wallet.external_balance = balance
        wallet.external_synced_at = timezone.now()
        wallet.save(update_fields=['external_balance', 'external_synced_at'])

        ExternalBalanceSyncLog.objects.create(
            user=user,
            fetched_balance=balance,
            source='php_backend',
            success=True,
        )
        return balance

    except Exception as exc:
        ExternalBalanceSyncLog.objects.create(
            user=user,
            fetched_balance=0,
            source='php_backend',
            success=False,
            error_message=str(exc),
        )
        return None


def push_transaction_to_php(user, amount, transaction_type, description, auth_token=None):
    """
    After we process a debit/credit on our end, push the update to the PHP
    backend so its wallet reflects the change.

    Expected PHP endpoint: POST /wallet/update
    Body: { "amount": 5000, "type": "debit"|"credit", "description": "..." }
    """
    headers = {'Content-Type': 'application/json'}
    if auth_token:
        headers['Authorization'] = f'Bearer {auth_token}'
    headers['X-Api-Key'] = PHP_BACKEND_API_KEY

    try:
        resp = requests.post(
            f'{PHP_BACKEND_URL}/wallet/update',
            json={
                'amount': float(amount),
                'type': transaction_type,
                'description': description,
            },
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        # Log but don't crash — our side is already updated
        print(f'[PHP sync error] {exc}')
        return None


# ─────────────────────────────────────────────────────────────────────
# NOTIFICATION HELPER
# ─────────────────────────────────────────────────────────────────────

def send_notification(user, notification_type, title, body, data=None):
    """Create a Notification record. Extend here to add FCM push later."""
    Notification.objects.create(
        user=user,
        type=notification_type,
        title=title,
        body=body,
        data=data or {},
    )
    # TODO: send FCM push notification
    # send_fcm_push(user, title, body, data)


# ─────────────────────────────────────────────────────────────────────
# ORDER HELPERS
# ─────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_order_from_items(buyer, items_data, delivery_info, external_transaction_id=None):
    """
    Create an Order + OrderItems + EscrowEntries from a list of cart items.
    items_data: [{'product_id': ..., 'variant_id': ..., 'quantity': ...}]
    """
    order = Order.objects.create(
        buyer=buyer,
        delivery_address=delivery_info.get('delivery_address', ''),
        delivery_state=delivery_info.get('delivery_state', ''),
        delivery_lga=delivery_info.get('delivery_lga', ''),
        notes=delivery_info.get('notes', ''),
        external_transaction_id=external_transaction_id,
        status='pending',
        payment_status='paid',
    )

    subtotal = Decimal('0')

    for item_data in items_data:
        try:
            product = Product.objects.get(id=item_data['product_id'], status='approved')
        except Product.DoesNotExist:
            continue

        variant = None
        if item_data.get('variant_id'):
            try:
                variant = ProductVariant.objects.get(id=item_data['variant_id'])
            except ProductVariant.DoesNotExist:
                pass

        unit_price = variant.price if variant else product.seller_price
        quantity = int(item_data.get('quantity', 1))

        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            seller=product.seller,
            variant=variant,
            product_name=product.name,
            product_image=_get_primary_image(product),
            unit_price=unit_price,
            commission_rate=product.commission_rate,
            quantity=quantity,
        )

        # Deduct stock
        if variant:
            variant.stock = max(0, variant.stock - quantity)
            variant.save(update_fields=['stock'])
        else:
            product.stock_count = max(0, product.stock_count - quantity)
            product.purchase_count += quantity
            product.save(update_fields=['stock_count', 'purchase_count'])

        # Hold earnings in escrow
        if product.seller:
            hold_in_escrow(
                seller=product.seller,
                order=order,
                order_item=order_item,
                amount=order_item.seller_earnings,
            )

            # Notify seller
            send_notification(
                user=product.seller.user,
                notification_type='order_new',
                title='New Order!',
                body=f'You have a new order for {product.name}',
                data={'order_id': str(order.id)},
            )

        subtotal += unit_price * quantity

    order.subtotal = subtotal
    order.grand_total = subtotal + order.delivery_fee
    order.save(update_fields=['subtotal', 'grand_total'])

    return order


def _get_primary_image(product):
    m = product.media.filter(is_primary=True).first() or product.media.first()
    return m.display_url if m else None


def release_escrow_for_order(order):
    """Release all held escrow for an order when it's delivered."""
    entries = EscrowEntry.objects.filter(order=order, status='holding')
    for entry in entries:
        entry.release()
        # Update seller stats
        seller = entry.seller
        seller.total_sales += 1
        seller.total_revenue += entry.amount
        seller.save(update_fields=['total_sales', 'total_revenue'])

        send_notification(
            user=seller.user,
            notification_type='escrow_release',
            title='Payment Released',
            body=f'₦{entry.amount} has been released to your wallet.',
            data={'order_id': str(order.id)},
        )


def refund_escrow_for_order(order):
    """Refund all held escrow when an order is cancelled."""
    entries = EscrowEntry.objects.filter(order=order, status='holding')
    for entry in entries:
        entry.refund()
        


