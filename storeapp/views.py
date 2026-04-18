# marketplace/views.py

from django.db import transaction
from django.db.models import Q, Avg
from django.utils import timezone
from django.contrib.auth.models import User

from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from .models import (
    Category, SellerProfile, Product, ProductMedia, ProductReceipt,
    ProductVariant, Order, OrderItem, SellerWallet, EscrowEntry,
    WalletTransaction, WithdrawalRequest, Cart, CartItem as CartItemModel,
    ProductReview, SellerReview, Notification,
)
from .serializers import (
    CategoryTreeSerializer, CategorySerializer,
    SellerProfileSerializer, SellerPublicSerializer,
    ProductListSerializer, ProductDetailSerializer,
    SellerProductSerializer, CreateProductSerializer,
    OrderSerializer, CreateOrderSerializer,
    SellerWalletSerializer, WalletTransactionSerializer,
    WithdrawalRequestSerializer, EscrowEntrySerializer,
    CartItemSerializer, ConfirmPricesSerializer,
    ProductReviewSerializer, NotificationSerializer,
)
from .helpers import (
    success_response, error_response, paginate_queryset,
    create_product_from_payload, get_or_create_wallet,
    credit_wallet, debit_wallet, sync_external_balance,
    push_transaction_to_php, send_notification,
    create_order_from_items, release_escrow_for_order,
    refund_escrow_for_order,
)


# ─────────────────────────────────────────────────────────────────────
# SHARED SWAGGER COMPONENTS
# ─────────────────────────────────────────────────────────────────────

_success = openapi.Response('Success', schema=openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'success': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=True),
        'message': openapi.Schema(type=openapi.TYPE_STRING, example='Success'),
        'data':    openapi.Schema(type=openapi.TYPE_OBJECT),
    },
))
_error_400 = openapi.Response('Bad Request — validation failed')
_error_401 = openapi.Response('Unauthorized — missing or invalid JWT token')
_error_403 = openapi.Response('Forbidden — seller profile inactive or missing')
_error_404 = openapi.Response('Not Found')
_error_500 = openapi.Response('Server Error')

_pagination_params = [
    openapi.Parameter('page',      openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Page number (default 1)'),
    openapi.Parameter('page_size', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Items per page (default 20)'),
]
# _auth_header = openapi.Parameter(
#     'Authorization', openapi.IN_HEADER,
#     description='Bearer <JWT token>',
#     type=openapi.TYPE_STRING,
#     required=True,
# )

# Reusable multipart listing body (POST /seller/listings/ and POST /admin/products/)
_listing_post_body = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    description='Send as multipart/form-data',
    properties={
        'data': openapi.Schema(
            type=openapi.TYPE_STRING,
            description=(
                'JSON string: name, description, condition (new|used|both), '
                'weight_kg, quantity, item_type (simple|variable), category, '
                'subcategory, seller_price, delivery { buyers_pickup, '
                'secondary_delivery, pickup_address, delivery_timeline, '
                'dispatch_state, state_lga_options[] }'
            ),
        ),
        'media[]':    openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_FILE)),
        'receipts[]': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_FILE)),
    },
    required=['data', 'media[]'],
)


# ─────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────

def _get_seller_or_error(user):
    seller = getattr(user, 'seller_profile', None)
    if not seller or not seller.is_active:
        return None, error_response('Seller profile not found or inactive.', 403)
    return seller, None


# ═════════════════════════════════════════════════════════════════════
# SECTION 1 — CATEGORIES
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='GET',
    operation_id='category_list',
    operation_summary='List all categories',
    operation_description=(
        'Returns the full category tree — top-level categories each containing '
        'their subcategories inline. Used to populate the filter sheet and the '
        'category picker in the Add Item flow. No authentication required.'
    ),
    tags=['Categories'],
    responses={200: _success},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def category_list(request):
    roots = Category.objects.filter(parent=None, is_active=True).prefetch_related('subcategories')
    data = CategoryTreeSerializer(roots, many=True).data
    return success_response(data)


@swagger_auto_schema(
    method='GET',
    operation_id='category_detail',
    operation_summary='Get a single category by slug',
    operation_description=(
        'Returns a single category object identified by its URL slug. '
        'Useful for deep-linking into a specific category browse page. '
        'No authentication required.'
    ),
    tags=['Categories'],
    responses={200: _success, 404: _error_404},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def category_detail(request, slug):
    try:
        cat = Category.objects.get(slug=slug, is_active=True)
    except Category.DoesNotExist:
        return error_response('Category not found.', 404)
    return success_response(CategorySerializer(cat).data)


# ═════════════════════════════════════════════════════════════════════
# SECTION 2 — PRODUCT FEEDS
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='GET',
    operation_id='hot_deals',
    operation_summary='Hot Deals product feed',
    operation_description=(
        'Returns paginated products flagged as Hot Deals (is_hot_deal=True) '
        'that are approved and available. Maps to hotDealsProvider in Flutter. '
        'No authentication required.'
    ),
    tags=['Product Feeds'],
    manual_parameters=_pagination_params,
    responses={200: _success},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def hot_deals(request):
    print('hot_deals called')
    qs = (
        Product.objects
        .filter(status='approved', is_hot_deal=True)
        .prefetch_related('media')
        .select_related('seller', 'category', 'subcategory')
    )
    result = paginate_queryset(qs, request, ProductListSerializer)
    return success_response(result)


@swagger_auto_schema(
    method='GET',
    operation_id='just_for_you',
    operation_summary='Just For You personalised feed',
    operation_description=(
        'Returns a personalised product feed. Currently returns quick-delivery '
        'products. Maps to justForYouProvider in Flutter. No authentication required.'
    ),
    tags=['Product Feeds'],
    manual_parameters=_pagination_params,
    responses={200: _success},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def just_for_you(request):
    qs = (
        Product.objects
        .filter(status='approved', is_quick_delivery=True)
        .prefetch_related('media')
        .select_related('seller', 'category', 'subcategory')
    )
    result = paginate_queryset(qs, request, ProductListSerializer)
    return success_response(result)


@swagger_auto_schema(
    method='GET',
    operation_id='explore',
    operation_summary='Explore / browse all products',
    operation_description=(
        'General browse feed returning all approved products. Supports filtering '
        'and sorting.\n\n'
        '**Filters:** `?category=` `?min_price=` `?max_price=` `?condition=new|used|both` '
        '`?delivery=buyers_pickup|sellers_delivery|yangaplug_delivery`\n\n'
        '**Sort:** `?sort=price_asc|price_desc|newest|popular|rating`'
    ),
    tags=['Product Feeds'],
    manual_parameters=_pagination_params + [
        openapi.Parameter('category',  openapi.IN_QUERY, type=openapi.TYPE_STRING),
        openapi.Parameter('min_price', openapi.IN_QUERY, type=openapi.TYPE_NUMBER),
        openapi.Parameter('max_price', openapi.IN_QUERY, type=openapi.TYPE_NUMBER),
        openapi.Parameter('condition', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='new | used | both'),
        openapi.Parameter('delivery',  openapi.IN_QUERY, type=openapi.TYPE_STRING),
        openapi.Parameter('sort',      openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          description='price_asc | price_desc | newest | popular | rating'),
    ],
    responses={200: _success},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def explore(request):
    qs = (
        Product.objects
        .filter(status='approved')
        .prefetch_related('media')
        .select_related('seller', 'category', 'subcategory')
    )
    category = request.query_params.get('category')
    if category:
        qs = qs.filter(Q(category__name__iexact=category) | Q(subcategory__name__iexact=category))
    min_price = request.query_params.get('min_price')
    max_price = request.query_params.get('max_price')
    if min_price:
        qs = qs.filter(seller_price__gte=min_price)
    if max_price:
        qs = qs.filter(seller_price__lte=max_price)
    condition = request.query_params.get('condition')
    if condition:
        qs = qs.filter(condition=condition)
    delivery = request.query_params.get('delivery')
    if delivery:
        qs = qs.filter(delivery_method=delivery)
    sort_map = {
        'price_asc': 'seller_price', 'price_desc': '-seller_price',
        'newest': '-created_at', 'popular': '-purchase_count', 'rating': '-rating',
    }
    qs = qs.order_by(sort_map.get(request.query_params.get('sort', ''), '-created_at'))
    result = paginate_queryset(qs, request, ProductListSerializer)
    return success_response(result)


@swagger_auto_schema(
    method='GET',
    operation_id='search_products',
    operation_summary='Search products',
    operation_description=(
        'Full-text search across product name, description, category, and subcategory. '
        'Results are ordered by purchase count then rating. '
        'No authentication required.\n\n'
        '**Query param:** `?q=<search term>`'
    ),
    tags=['Product Feeds'],
    manual_parameters=_pagination_params + [
        openapi.Parameter('q', openapi.IN_QUERY, type=openapi.TYPE_STRING, required=True),
    ],
    responses={200: _success},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def search_products(request):
    q = request.query_params.get('q', '').strip()
    if not q:
        return success_response({'results': [], 'count': 0, 'next': None, 'previous': None})
    qs = (
        Product.objects
        .filter(
            Q(name__icontains=q) | Q(description__icontains=q) |
            Q(category__name__icontains=q) | Q(subcategory__name__icontains=q),
            status='approved',
        )
        .prefetch_related('media')
        .select_related('seller', 'category', 'subcategory')
        .order_by('-purchase_count', '-rating')
    )
    result = paginate_queryset(qs, request, ProductListSerializer)
    return success_response(result)


@swagger_auto_schema(
    method='GET',
    operation_id='product_detail',
    operation_summary='Get product detail',
    operation_description=(
        'Returns full detail for a single approved product including media, variants, '
        'seller info, delivery options, and commission breakdown. '
        'Increments view count on each call. No authentication required.'
    ),
    tags=['Product Feeds'],
    responses={200: _success, 404: _error_404},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def product_detail(request, product_id):
    try:
        product = (
            Product.objects
            .select_related('seller', 'category', 'subcategory')
            .prefetch_related('media', 'variants', 'receipts')
            .get(id=product_id, status='approved')
        )
    except Product.DoesNotExist:
        return error_response('Product not found.', 404)
    Product.objects.filter(id=product_id).update(view_count=product.view_count + 1)
    data = ProductDetailSerializer(product, context={'request': request}).data
    return success_response(data)


@swagger_auto_schema(
    method='GET',
    operation_id='recommended_products',
    operation_summary='Recommended products',
    operation_description=(
        'Returns up to 12 products in the same category as the reference product, '
        'excluding the product itself. Used on the product detail page. '
        'Falls back to globally popular products if no product_id is given. '
        'No authentication required.'
    ),
    tags=['Product Feeds'],
    responses={200: _success},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def recommended_products(request, product_id=None):
    qs = Product.objects.filter(status='approved').prefetch_related('media').select_related('category')
    if product_id:
        try:
            ref = Product.objects.get(id=product_id)
            qs = qs.filter(category=ref.category).exclude(id=product_id)
        except Product.DoesNotExist:
            pass
    qs = qs.order_by('-rating', '-purchase_count')[:12]
    data = ProductListSerializer(qs, many=True, context={'request': request}).data
    return success_response(data)


@swagger_auto_schema(
    method='GET',
    operation_id='seller_public_profile',
    operation_summary='Get seller public profile',
    operation_description=(
        'Returns the publicly visible seller profile shown on the product detail page. '
        'Includes display name, avatar, location, rating, total sales, review count, '
        'and verification status. No authentication required.'
    ),
    tags=['Product Feeds'],
    responses={200: _success, 404: _error_404},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def seller_public_profile(request, seller_id):
    try:
        seller = SellerProfile.objects.get(id=seller_id, is_active=True)
    except SellerProfile.DoesNotExist:
        return error_response('Seller not found.', 404)
    return success_response(SellerPublicSerializer(seller).data)


@swagger_auto_schema(
    method='GET',
    operation_id='product_reviews',
    operation_summary='List reviews for a product',
    operation_description=(
        'Returns paginated reviews for the given product. Each review includes rating, '
        'comment, buyer name, and whether the review is from a verified purchaser. '
        'No authentication required.'
    ),
    tags=['Reviews'],
    manual_parameters=_pagination_params,
    responses={200: _success},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def product_reviews(request, product_id):
    reviews = ProductReview.objects.filter(product_id=product_id).select_related('buyer')
    result = paginate_queryset(reviews, request, ProductReviewSerializer)
    return success_response(result)


# ═════════════════════════════════════════════════════════════════════
# SECTION 3 — CATALOG
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='GET',
    operation_id='catalog_products',
    operation_summary='Browse the admin catalog',
    operation_description=(
        'Returns paginated admin-published catalog products that sellers can use '
        'as a base to create their own listings. Supports search and category filter. '
        '**Requires authentication.**\n\n'
        '**Query params:** `?q=<search>` `?category=<name>`'
    ),
    tags=['Catalog'],
    manual_parameters= _pagination_params + [
        openapi.Parameter('q',        openapi.IN_QUERY, type=openapi.TYPE_STRING),
        openapi.Parameter('category', openapi.IN_QUERY, type=openapi.TYPE_STRING),
    ],
    responses={200: _success, 401: _error_401},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def catalog_products(request):
    qs = (
        Product.objects
        .filter(source='admin', status='approved')
        .prefetch_related('media')
        .select_related('category', 'subcategory')
        .order_by('-created_at')
    )
    q = request.query_params.get('q', '').strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(category__name__icontains=q))
    category = request.query_params.get('category')
    if category:
        qs = qs.filter(Q(category__name__iexact=category) | Q(subcategory__name__iexact=category))
    result = paginate_queryset(qs, request, ProductDetailSerializer)
    return success_response(result)


@swagger_auto_schema(
    method='GET',
    operation_id='catalog_product_detail',
    operation_summary='Get a single catalog product',
    operation_description=(
        'Returns full detail for a single admin-published catalog product. '
        'Used when a seller selects a product from the catalog to base their listing on. '
        '**Requires authentication.**'
    ),
    tags=['Catalog'],
    responses={200: _success, 401: _error_401, 404: _error_404},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def catalog_product_detail(request, product_id):
    try:
        product = Product.objects.get(id=product_id, source='admin', status='approved')
    except Product.DoesNotExist:
        return error_response('Catalog product not found.', 404)
    return success_response(ProductDetailSerializer(product, context={'request': request}).data)


# ═════════════════════════════════════════════════════════════════════
# SECTION 4 — SELLER PROFILE
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='POST',
    operation_id='seller_onboard',
    operation_summary='Create a seller profile (onboarding)',
    operation_description=(
        'Creates a SellerProfile for the authenticated user. Must be called once '
        'before the user can create listings, manage orders, or access wallet features. '
        'Returns 400 if a profile already exists.\n\n'
        '**Body:** `display_name` (required), `phone`, `bio`, `location`, `state`'
    ),
    tags=['Seller — Profile'],
    request_body=SellerProfileSerializer,
    responses={201: _success, 400: _error_400, 401: _error_401},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def seller_onboard(request):
    if hasattr(request.user, 'seller_profile'):
        return error_response('Seller profile already exists.', 400)
    ser = SellerProfileSerializer(data=request.data)
    if ser.is_valid():
        ser.save(user=request.user)
        return success_response(ser.data, 'Seller profile created.', 201)
    return error_response('Validation failed.', 400, errors=ser.errors)


# ── seller_profile handles GET / PUT / PATCH — each needs its own decorator ──

@swagger_auto_schema(
    method='GET',
    operation_id='seller_profile_get',
    operation_summary='Get own seller profile',
    operation_description=(
        'Returns the authenticated seller\'s full profile including verification '
        'status, commission rate, total sales, and rating.'
    ),
    tags=['Seller — Profile'],
    responses={200: _success, 401: _error_401, 403: _error_403, 404: _error_404},
)
@swagger_auto_schema(
    method='PUT',
    operation_id='seller_profile_put',
    operation_summary='Full update of seller profile',
    operation_description=(
        'Full profile update — all fields must be provided. '
        'Fields that cannot be updated: `verification_status`, `commission_rate`, '
        '`total_sales`, `total_revenue`, `rating`, `review_count`.'
    ),
    tags=['Seller — Profile'],
    request_body=SellerProfileSerializer,
    responses={200: _success, 400: _error_400, 401: _error_401, 403: _error_403},
)
@swagger_auto_schema(
    method='PATCH',
    operation_id='seller_profile_patch',
    operation_summary='Partial update of seller profile',
    operation_description='Partial profile update — only send the fields you want to change.',
    tags=['Seller — Profile'],
    request_body=SellerProfileSerializer,
    responses={200: _success, 400: _error_400, 401: _error_401, 403: _error_403},
)
@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def seller_profile(request):
    seller, err = _get_seller_or_error(request.user)
    if err:
        if request.method == 'GET':
            return error_response('Seller profile not found. Please complete onboarding.', 404)
        return err
    if request.method == 'GET':
        return success_response(SellerProfileSerializer(seller).data)
    partial = request.method == 'PATCH'
    ser = SellerProfileSerializer(seller, data=request.data, partial=partial)
    if ser.is_valid():
        ser.save()
        return success_response(ser.data, 'Profile updated.')
    return error_response('Validation failed.', 400, errors=ser.errors)


@swagger_auto_schema(
    method='GET',
    operation_id='commission_rate',
    operation_summary='Get seller commission rate',
    operation_description=(
        'Returns the current commission rate for this seller. '
        'Called at the start of the listing flow to populate the pricing step '
        'commission breakdown. Example: `{ "commission_rate": 0.05 }` = 5%.'
    ),
    tags=['Seller — Profile'],
    responses={200: _success, 401: _error_401, 403: _error_403},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def commission_rate(request):
    seller, err = _get_seller_or_error(request.user)
    if err:
        return err
    return success_response({'commission_rate': float(seller.commission_rate)})


# ═════════════════════════════════════════════════════════════════════
# SECTION 5 — SELLER LISTINGS
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='GET',
    operation_id='seller_listings_get',
    operation_summary='List seller\'s own listings',
    operation_description=(
        'Returns paginated listings owned by the authenticated seller. '
        'Filter by `?status=pending|approved|rejected|draft|archived`.'
    ),
    tags=['Seller — Listings'] + _pagination_params + [
        openapi.Parameter('status', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          description='pending | approved | rejected | draft | archived'),
    ],
    responses={200: _success, 401: _error_401, 403: _error_403},
)
@swagger_auto_schema(
    method='POST',
    operation_id='seller_listings_post',
    operation_summary='Create a new listing',
    operation_description=(
        'Creates a new product listing submitted for admin review. '
        'Works for both catalog-based and create-your-own listing routes. '
        'Send as `multipart/form-data`.\n\n'
        '**Fields:**\n'
        '- `data` — JSON string (see schema)\n'
        '- `media[]` — image/video files\n'
        '- `receipts[]` — optional receipt images for luxury items\n\n'
        'The listing is created with `status=pending`. '
        'The seller receives a confirmation notification.'
    ),
    tags=['Seller — Listings'],
    request_body=_listing_post_body,
    responses={201: _success, 400: _error_400, 401: _error_401, 403: _error_403, 500: _error_500},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def seller_listings(request):
    seller, err = _get_seller_or_error(request.user)
    if err:
        return err

    if request.method == 'GET':
        status_filter = request.query_params.get('status')
        qs = seller.products.prefetch_related('media').order_by('-created_at')
        if status_filter:
            qs = qs.filter(status=status_filter)
        result = paginate_queryset(qs, request, SellerProductSerializer)
        return success_response(result)

    import json
    raw = request.data.get('data')
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return error_response('Invalid JSON in "data" field.', 400)
    else:
        payload = request.data

    ser = CreateProductSerializer(data=payload)
    if not ser.is_valid():
        return error_response('Validation failed.', 400, errors=ser.errors)

    media_files = request.FILES.getlist('media[]') or request.FILES.getlist('media')
    receipt_files = request.FILES.getlist('receipts[]') or request.FILES.getlist('receipts')

    try:
        product = create_product_from_payload(seller, ser.validated_data, media_files, receipt_files)
    except Exception as exc:
        return error_response(f'Failed to create listing: {exc}', 500)

    send_notification(
        user=request.user,
        notification_type='system',
        title='Listing Submitted',
        body=f'Your listing "{product.name}" is under review.',
        data={'product_id': str(product.id)},
    )

    return success_response(
        SellerProductSerializer(product, context={'request': request}).data,
        'Listing submitted for review.',
        201,
    )


@swagger_auto_schema(
    method='GET',
    operation_id='seller_listing_detail_get',
    operation_summary='Get a single seller listing',
    operation_description='Returns full detail of one listing owned by the authenticated seller.',
    tags=['Seller — Listings'],
    responses={200: _success, 401: _error_401, 403: _error_403, 404: _error_404},
)
@swagger_auto_schema(
    method='PUT',
    operation_id='seller_listing_detail_put',
    operation_summary='Update a listing (full)',
    operation_description=(
        'Full update of a listing. Only allowed when status is `draft` or `rejected`. '
        'Saves and re-submits for review (sets status back to `pending`). '
        'Updatable fields: `name`, `description`, `seller_price`, `stock_count`, `weight_kg`. '
        'Attach new media via `media[]` files in multipart.'
    ),
    tags=['Seller — Listings'],
    request_body=_listing_post_body,
    responses={200: _success, 400: _error_400, 401: _error_401, 403: _error_403, 404: _error_404},
)
@swagger_auto_schema(
    method='PATCH',
    operation_id='seller_listing_detail_patch',
    operation_summary='Update a listing (partial)',
    operation_description=(
        'Partial update of a listing. Same rules as PUT — only allowed when status '
        'is `draft` or `rejected`. Re-submits for review on save.'
    ),
    tags=['Seller — Listings'],
    request_body=_listing_post_body,
    responses={200: _success, 400: _error_400, 401: _error_401, 403: _error_403, 404: _error_404},
)
@swagger_auto_schema(
    method='DELETE',
    operation_id='seller_listing_detail_delete',
    operation_summary='Delete or archive a listing',
    operation_description=(
        'If the listing is `pending` or `approved`, it is archived instead of deleted. '
        'Draft and rejected listings are permanently deleted.'
    ),
    tags=['Seller — Listings'],
    responses={200: _success, 401: _error_401, 403: _error_403, 404: _error_404},
)
@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def seller_listing_detail(request, product_id):
    seller, err = _get_seller_or_error(request.user)
    if err:
        return err
    try:
        product = seller.products.get(id=product_id)
    except Product.DoesNotExist:
        return error_response('Listing not found.', 404)

    if request.method == 'GET':
        return success_response(SellerProductSerializer(product, context={'request': request}).data)

    if request.method == 'DELETE':
        if product.status in ('approved', 'pending'):
            product.status = 'archived'
            product.save(update_fields=['status'])
            return success_response(message='Listing archived.')
        product.delete()
        return success_response(message='Listing deleted.')

    import json
    raw = request.data.get('data')
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return error_response('Invalid JSON in "data" field.', 400)
    else:
        payload = request.data.dict() if hasattr(request.data, 'dict') else dict(request.data)

    if product.status not in ('draft', 'rejected'):
        return error_response(f'Listing cannot be edited while status is "{product.status}".', 403)

    for field in ['name', 'description', 'seller_price', 'stock_count', 'weight_kg']:
        if field in payload:
            setattr(product, field, payload[field])

    product.status = 'pending'
    product.save()

    new_media = request.FILES.getlist('media[]') or request.FILES.getlist('media')
    for idx, f in enumerate(new_media):
        ext = f.name.rsplit('.', 1)[-1].lower()
        media_type = 'video' if ext in ('mp4', 'mov', 'avi') else 'image'
        ProductMedia.objects.create(product=product, file=f, media_type=media_type, order=100 + idx)

    return success_response(
        SellerProductSerializer(product, context={'request': request}).data,
        'Listing updated and re-submitted for review.',
    )


@swagger_auto_schema(
    method='DELETE',
    operation_id='delete_product_media',
    operation_summary='Delete a media file from a listing',
    operation_description=(
        'Permanently deletes a single image or video attached to a listing. '
        'Only the listing owner can remove media. '
        'Use the media `id` from the listing detail response.'
    ),
    tags=['Seller — Listings'],
    responses={200: _success, 401: _error_401, 403: _error_403, 404: _error_404},
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_product_media(request, product_id, media_id):
    seller, err = _get_seller_or_error(request.user)
    if err:
        return err
    try:
        media = ProductMedia.objects.get(id=media_id, product__id=product_id, product__seller=seller)
    except ProductMedia.DoesNotExist:
        return error_response('Media not found.', 404)
    media.delete()
    return success_response(message='Media deleted.')


# ═════════════════════════════════════════════════════════════════════
# SECTION 6 — ADMIN PRODUCT MANAGEMENT
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='GET',
    operation_id='admin_products_get',
    operation_summary='[Admin] List all products',
    operation_description=(
        'Returns all products across all statuses. '
        'Filter by `?status=pending|approved|rejected|draft|archived` to work the review queue. '
        '**Requires Django staff/admin status.**'
    ),
    tags=['Admin'],
    manual_parameters= _pagination_params + [
        openapi.Parameter('status', openapi.IN_QUERY, type=openapi.TYPE_STRING),
    ],
    responses={200: _success, 401: _error_401},
)
@swagger_auto_schema(
    method='POST',
    operation_id='admin_products_post',
    operation_summary='[Admin] Publish a catalog product',
    operation_description=(
        'Publishes a new admin catalog product directly with `status=approved`. '
        'These appear in `GET /catalog/products/` for sellers to list from. '
        'Same multipart payload as the seller listing endpoint. '
        '**Requires Django staff/admin status.**'
    ),
    tags=['Admin'],
    request_body=_listing_post_body,
    responses={201: _success, 400: _error_400, 401: _error_401},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_products(request):
    if request.method == 'GET':
        status_filter = request.query_params.get('status')
        qs = (
            Product.objects
            .select_related('seller', 'category', 'subcategory')
            .prefetch_related('media')
            .order_by('-created_at')
        )
        if status_filter:
            qs = qs.filter(status=status_filter)
        result = paginate_queryset(qs, request, SellerProductSerializer)
        return success_response(result)

    import json
    raw = request.data.get('data')
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return error_response('Invalid JSON.', 400)
    else:
        payload = request.data

    ser = CreateProductSerializer(data=payload)
    if not ser.is_valid():
        return error_response('Validation failed.', 400, errors=ser.errors)

    media_files = request.FILES.getlist('media[]') or request.FILES.getlist('media')
    receipt_files = request.FILES.getlist('receipts[]') or request.FILES.getlist('receipts')

    product = create_product_from_payload(None, ser.validated_data, media_files, receipt_files)
    product.source = 'admin'
    product.status = 'approved'
    product.published_by = request.user
    product.approved_at = timezone.now()
    product.save(update_fields=['source', 'status', 'published_by', 'approved_at'])

    return success_response(
        ProductDetailSerializer(product, context={'request': request}).data,
        'Catalog product published.',
        201,
    )


@swagger_auto_schema(
    method='PUT',
    operation_id='admin_approve_product',
    operation_summary='[Admin] Approve a seller listing',
    operation_description=(
        'Approves a pending listing and makes it live. Optionally sets display flags '
        'and an admin note. Triggers a push notification to the seller. '
        '**Requires Django staff/admin status.**\n\n'
        '**Optional body fields:** `is_hot_deal`, `is_featured`, '
        '`is_quick_delivery`, `is_new_arrival` (booleans), `admin_note` (string)'
    ),
    tags=['Admin'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'is_hot_deal':       openapi.Schema(type=openapi.TYPE_BOOLEAN),
            'is_featured':       openapi.Schema(type=openapi.TYPE_BOOLEAN),
            'is_quick_delivery': openapi.Schema(type=openapi.TYPE_BOOLEAN),
            'is_new_arrival':    openapi.Schema(type=openapi.TYPE_BOOLEAN),
            'admin_note':        openapi.Schema(type=openapi.TYPE_STRING),
        },
    ),
    responses={200: _success, 401: _error_401, 404: _error_404},
)
@api_view(['PUT'])
@permission_classes([IsAdminUser])
def admin_approve_product(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return error_response('Product not found.', 404)
    product.status = 'approved'
    product.approved_at = timezone.now()
    for flag in ('is_hot_deal', 'is_featured', 'is_quick_delivery', 'is_new_arrival'):
        if flag in request.data:
            setattr(product, flag, request.data[flag])
    if 'admin_note' in request.data:
        product.admin_note = request.data['admin_note']
    product.save()
    if product.seller:
        send_notification(
            user=product.seller.user,
            notification_type='product_approved',
            title='Listing Approved!',
            body=f'"{product.name}" is now live on the marketplace.',
            data={'product_id': str(product.id)},
        )
    return success_response(message='Product approved.')


@swagger_auto_schema(
    method='PUT',
    operation_id='admin_reject_product',
    operation_summary='[Admin] Reject a seller listing',
    operation_description=(
        'Rejects a pending listing. The reason is stored as an admin note and '
        'sent to the seller via notification. The seller can then edit and re-submit. '
        '**Requires Django staff/admin status.**\n\n'
        '**Body:** `reason` (string, required)'
    ),
    tags=['Admin'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['reason'],
        properties={
            'reason': openapi.Schema(type=openapi.TYPE_STRING),
        },
    ),
    responses={200: _success, 401: _error_401, 404: _error_404},
)
@api_view(['PUT'])
@permission_classes([IsAdminUser])
def admin_reject_product(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return error_response('Product not found.', 404)
    reason = request.data.get('reason', '')
    product.status = 'rejected'
    product.admin_note = reason
    product.save(update_fields=['status', 'admin_note'])
    if product.seller:
        send_notification(
            user=product.seller.user,
            notification_type='product_rejected',
            title='Listing Rejected',
            body=f'"{product.name}" was rejected. Reason: {reason}',
            data={'product_id': str(product.id)},
        )
    return success_response(message='Product rejected.')


@swagger_auto_schema(
    method='PUT',
    operation_id='admin_update_product_flags',
    operation_summary='[Admin] Update product display flags',
    operation_description=(
        'Toggles display flags without changing the product status. '
        'Use to add/remove a product from Hot Deals, Featured, Quick Delivery, '
        'or New Arrivals sections. **Requires Django staff/admin status.**\n\n'
        '**Optional body fields (all boolean):** '
        '`is_hot_deal`, `is_featured`, `is_quick_delivery`, `is_new_arrival`'
    ),
    tags=['Admin'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'is_hot_deal':       openapi.Schema(type=openapi.TYPE_BOOLEAN),
            'is_featured':       openapi.Schema(type=openapi.TYPE_BOOLEAN),
            'is_quick_delivery': openapi.Schema(type=openapi.TYPE_BOOLEAN),
            'is_new_arrival':    openapi.Schema(type=openapi.TYPE_BOOLEAN),
        },
    ),
    responses={200: _success, 401: _error_401, 404: _error_404},
)
@api_view(['PUT'])
@permission_classes([IsAdminUser])
def admin_update_product_flags(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return error_response('Product not found.', 404)
    flags = ['is_hot_deal', 'is_featured', 'is_quick_delivery', 'is_new_arrival']
    changed = [f for f in flags if f in request.data]
    for flag in changed:
        setattr(product, flag, request.data[flag])
    if changed:
        product.save(update_fields=changed)
    return success_response(message='Flags updated.')


# ═════════════════════════════════════════════════════════════════════
# SECTION 7 — CART
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='GET',
    operation_id='cart_detail',
    operation_summary='Get server-side cart',
    operation_description=(
        'Returns the server-side cart for the authenticated buyer. '
        'Flutter stores cart state locally but calls this on app open to sync. '
        'Each item includes the confirmed live price.'
    ),
    tags=['Cart'],
    responses={200: _success, 401: _error_401},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def cart_detail(request):
    cart, _ = Cart.objects.get_or_create(buyer=request.user)
    items = cart.items.select_related('product', 'variant').all()
    data = CartItemSerializer(items, many=True, context={'request': request}).data
    return success_response({'items': data, 'count': items.count()})


@swagger_auto_schema(
    method='POST',
    operation_id='cart_confirm_prices',
    operation_summary='Confirm live prices for cart items',
    operation_description=(
        'Accepts a list of product IDs and returns their current live prices. '
        'Flutter calls this when the cart screen opens. '
        'Products not found or not approved are omitted from the response.\n\n'
        '**Body:** `{ "product_ids": ["uuid1", "uuid2"] }`\n\n'
        '**Response:** `{ "prices": { "uuid1": 50000.0 } }`'
    ),
    tags=['Cart'],
    request_body=ConfirmPricesSerializer,
    responses={200: _success, 400: _error_400, 401: _error_401},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cart_confirm_prices(request):
    ser = ConfirmPricesSerializer(data=request.data)
    if not ser.is_valid():
        return error_response('Invalid payload.', 400, errors=ser.errors)
    products = Product.objects.filter(id__in=ser.validated_data['product_ids'], status='approved')
    prices = {str(p.id): float(p.seller_price) for p in products}
    return success_response({'prices': prices})


# ═════════════════════════════════════════════════════════════════════
# SECTION 8 — ORDERS
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='GET',
    operation_id='orders_get',
    operation_summary='List buyer order history',
    operation_description=(
        'Returns the authenticated buyer\'s full order history, newest first. '
        'Each order includes all items, delivery info, and payment status.'
    ),
    tags=['Orders'],
    manual_parameters= _pagination_params,
    responses={200: _success, 401: _error_401},
)
@swagger_auto_schema(
    method='POST',
    operation_id='orders_post',
    operation_summary='Place a new order',
    operation_description=(
        'Creates an order from the buyer\'s cart. Automatically deducts stock, '
        'places seller earnings into escrow, and notifies each seller. '
        'The `external_transaction_id` should be the payment reference from the PHP backend.\n\n'
        '**Body:** `delivery_address`, `delivery_state`, `delivery_lga`, `notes` (optional), '
        '`external_transaction_id` (optional), '
        '`items: [{ product_id, variant_id?, quantity }]`'
    ),
    tags=['Orders'],
    request_body=CreateOrderSerializer,
    responses={201: _success, 400: _error_400, 401: _error_401, 500: _error_500},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def orders(request):
    if request.method == 'GET':
        qs = (
            Order.objects
            .filter(buyer=request.user)
            .prefetch_related('items')
            .order_by('-created_at')
        )
        result = paginate_queryset(qs, request, OrderSerializer)
        return success_response(result)

    ser = CreateOrderSerializer(data=request.data)
    if not ser.is_valid():
        return error_response('Validation failed.', 400, errors=ser.errors)

    try:
        order = create_order_from_items(
            buyer=request.user,
            items_data=ser.validated_data['items'],
            delivery_info=ser.validated_data,
            external_transaction_id=ser.validated_data.get('external_transaction_id'),
        )
    except Exception as exc:
        return error_response(f'Order creation failed: {exc}', 500)

    return success_response(OrderSerializer(order).data, 'Order placed.', 201)


@swagger_auto_schema(
    method='GET',
    operation_id='order_detail',
    operation_summary='Get a single order',
    operation_description=(
        'Returns full detail of one order belonging to the authenticated buyer, '
        'including all items, price snapshots, delivery info, and tracking number.'
    ),
    tags=['Orders'],
    responses={200: _success, 401: _error_401, 404: _error_404},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def order_detail(request, order_id):
    try:
        order = Order.objects.prefetch_related('items').get(id=order_id, buyer=request.user)
    except Order.DoesNotExist:
        return error_response('Order not found.', 404)
    return success_response(OrderSerializer(order).data)


@swagger_auto_schema(
    method='PUT',
    operation_id='update_order_status',
    operation_summary='Mark order as delivered or cancel it',
    operation_description=(
        'Buyers use this to update their own order status.\n\n'
        '`delivered` — triggers escrow release; seller earnings move to available balance.\n\n'
        '`cancelled` — only allowed when status is `pending` or `confirmed`; '
        'triggers escrow refund.\n\n'
        '**Body:** `{ "status": "delivered" | "cancelled" }`'
    ),
    tags=['Orders'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['status'],
        properties={
            'status': openapi.Schema(type=openapi.TYPE_STRING, enum=['delivered', 'cancelled']),
        },
    ),
    responses={200: _success, 400: _error_400, 401: _error_401, 404: _error_404},
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_order_status(request, order_id):
    try:
        order = Order.objects.get(id=order_id, buyer=request.user)
    except Order.DoesNotExist:
        return error_response('Order not found.', 404)

    new_status = request.data.get('status')
    if new_status not in ('delivered', 'cancelled'):
        return error_response('Invalid status. Use "delivered" or "cancelled".', 400)

    if new_status == 'delivered':
        order.status = 'delivered'
        order.delivered_at = timezone.now()
        order.save(update_fields=['status', 'delivered_at'])
        release_escrow_for_order(order)
    elif new_status == 'cancelled':
        if order.status not in ('pending', 'confirmed'):
            return error_response('Order cannot be cancelled at this stage.', 400)
        order.status = 'cancelled'
        order.save(update_fields=['status'])
        refund_escrow_for_order(order)

    return success_response(message=f'Order marked as {new_status}.')


@swagger_auto_schema(
    method='GET',
    operation_id='seller_orders',
    operation_summary='Get orders containing the seller\'s items',
    operation_description=(
        'Returns all orders containing at least one item from the authenticated seller. '
        'Filter by `?status=pending|confirmed|processing|shipped|delivered|cancelled`.'
    ),
    tags=['Seller — Orders'],
    manual_parameters= _pagination_params + [
        openapi.Parameter('status', openapi.IN_QUERY, type=openapi.TYPE_STRING),
    ],
    responses={200: _success, 401: _error_401, 403: _error_403},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def seller_orders(request):
    seller, err = _get_seller_or_error(request.user)
    if err:
        return err
    order_ids = OrderItem.objects.filter(seller=seller).values_list('order_id', flat=True).distinct()
    qs = Order.objects.filter(id__in=order_ids).prefetch_related('items').order_by('-created_at')
    status_filter = request.query_params.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)
    result = paginate_queryset(qs, request, OrderSerializer)
    return success_response(result)


@swagger_auto_schema(
    method='PUT',
    operation_id='seller_update_order_status',
    operation_summary='Update order status as a seller',
    operation_description=(
        'Sellers can move an order through: `confirmed` → `processing` → `shipped`. '
        'Sellers cannot mark orders as `delivered` — only buyers can, which triggers escrow release. '
        'Sends a push notification to the buyer on each update.\n\n'
        '**Body:** `{ "status": "confirmed"|"processing"|"shipped", "tracking_number"?: "..." }`'
    ),
    tags=['Seller — Orders'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['status'],
        properties={
            'status':           openapi.Schema(type=openapi.TYPE_STRING, enum=['confirmed', 'processing', 'shipped']),
            'tracking_number':  openapi.Schema(type=openapi.TYPE_STRING),
        },
    ),
    responses={200: _success, 400: _error_400, 401: _error_401, 403: _error_403, 404: _error_404},
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def seller_update_order_status(request, order_id):
    seller, err = _get_seller_or_error(request.user)
    if err:
        return err
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return error_response('Order not found.', 404)
    if not order.items.filter(seller=seller).exists():
        return error_response('Forbidden.', 403)
    allowed = ('confirmed', 'processing', 'shipped')
    new_status = request.data.get('status')
    if new_status not in allowed:
        return error_response(f'Seller can only set status to: {", ".join(allowed)}.', 400)
    order.status = new_status
    tracking = request.data.get('tracking_number')
    if tracking:
        order.tracking_number = tracking
    order.save(update_fields=['status', 'tracking_number'])
    send_notification(
        user=order.buyer,
        notification_type='order_update',
        title='Order Update',
        body=f'Your order #{order.order_number} is now "{new_status}".',
        data={'order_id': str(order.id)},
    )
    return success_response(message=f'Order updated to {new_status}.')


# ═════════════════════════════════════════════════════════════════════
# SECTION 9 — WALLET
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='GET',
    operation_id='wallet_detail',
    operation_summary='Get seller wallet balances',
    operation_description=(
        'Returns the seller\'s wallet balances:\n\n'
        '- `available_balance` — withdrawable now\n'
        '- `escrow_balance` — locked pending buyer delivery confirmation\n'
        '- `total_earned` — lifetime credits\n'
        '- `total_withdrawn` — lifetime withdrawals\n'
        '- `external_balance` — last known PHP backend balance\n'
        '- `external_synced_at` — timestamp of last sync'
    ),
    tags=['Wallet'],
    responses={200: _success, 401: _error_401, 403: _error_403},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_detail(request):
    seller, err = _get_seller_or_error(request.user)
    if err:
        return err
    wallet = get_or_create_wallet(seller)
    return success_response(SellerWalletSerializer(wallet).data)


@swagger_auto_schema(
    method='POST',
    operation_id='wallet_sync',
    operation_summary='Sync external balance from PHP backend',
    operation_description=(
        'Fetches the user\'s balance from the PHP backend and stores it as '
        '`external_balance` on the wallet. Pass the PHP token in the body or '
        'as an `X-PHP-Token` header. Call after login and periodically.\n\n'
        '**Body (optional):** `{ "auth_token": "<PHP token>" }`'
    ),
    tags=['Wallet'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'auth_token': openapi.Schema(type=openapi.TYPE_STRING),
        },
    ),
    responses={200: _success, 401: _error_401, 502: openapi.Response('PHP backend unreachable')},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def wallet_sync(request):
    auth_token = request.data.get('auth_token') or request.META.get('HTTP_X_PHP_TOKEN')
    balance = sync_external_balance(request.user, auth_token=auth_token)
    if balance is None:
        return error_response('Failed to sync balance from external backend.', 502)
    return success_response({'external_balance': float(balance)}, 'Balance synced.')


@swagger_auto_schema(
    method='GET',
    operation_id='wallet_transactions',
    operation_summary='Get wallet transaction history',
    operation_description=(
        'Returns paginated transaction history for the seller\'s wallet.\n\n'
        '**Filters:** `?type=credit|debit` '
        '`?category=sale|escrow_release|withdrawal|refund|adjustment`'
    ),
    tags=['Wallet'],
    manual_parameters= _pagination_params + [
        openapi.Parameter('type',     openapi.IN_QUERY, type=openapi.TYPE_STRING, description='credit | debit'),
        openapi.Parameter('category', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          description='sale | escrow_release | withdrawal | refund | adjustment'),
    ],
    responses={200: _success, 401: _error_401, 403: _error_403},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_transactions(request):
    seller, err = _get_seller_or_error(request.user)
    if err:
        return err
    wallet = get_or_create_wallet(seller)
    qs = wallet.transactions.order_by('-created_at')
    if request.query_params.get('type'):
        qs = qs.filter(transaction_type=request.query_params['type'])
    if request.query_params.get('category'):
        qs = qs.filter(category=request.query_params['category'])
    result = paginate_queryset(qs, request, WalletTransactionSerializer)
    return success_response(result)


@swagger_auto_schema(
    method='POST',
    operation_id='request_withdrawal',
    operation_summary='Request a withdrawal',
    operation_description=(
        'Submits a withdrawal request. The amount is deducted from available balance immediately '
        'and queued for admin processing.\n\n'
        '`destination=bank` → requires `bank_name`, `account_number`, `account_name`\n\n'
        '`destination=wallet` → requires `wallet_id` (PHP backend wallet ID)\n\n'
        'Returns 400 if the requested amount exceeds available balance.'
    ),
    tags=['Wallet'],
    request_body=WithdrawalRequestSerializer,
    responses={201: _success, 400: _error_400, 401: _error_401, 403: _error_403},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_withdrawal(request):
    seller, err = _get_seller_or_error(request.user)
    if err:
        return err
    ser = WithdrawalRequestSerializer(data=request.data)
    if not ser.is_valid():
        return error_response('Validation failed.', 400, errors=ser.errors)
    wallet = get_or_create_wallet(seller)
    amount = ser.validated_data['amount']
    if wallet.available_balance < amount:
        return error_response('Insufficient available balance.', 400)
    wallet.available_balance -= amount
    wallet.total_withdrawn += amount
    wallet.save(update_fields=['available_balance', 'total_withdrawn'])
    withdrawal = ser.save(seller=seller)
    WalletTransaction.objects.create(
        wallet=wallet,
        transaction_type='debit',
        category='withdrawal',
        amount=amount,
        description=f'Withdrawal request to {ser.validated_data["destination"]}',
        reference_id=str(withdrawal.id),
        status='pending',
    )
    send_notification(
        user=request.user,
        notification_type='payment',
        title='Withdrawal Requested',
        body=f'Your withdrawal of ₦{amount} is being processed.',
        data={'withdrawal_id': str(withdrawal.id)},
    )
    return success_response(ser.data, 'Withdrawal request submitted.', 201)


@swagger_auto_schema(
    method='GET',
    operation_id='withdrawal_history',
    operation_summary='Get withdrawal request history',
    operation_description='Returns paginated withdrawal requests for the authenticated seller, newest first.',
    tags=['Wallet'],
    manual_parameters= _pagination_params,
    responses={200: _success, 401: _error_401, 403: _error_403},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def withdrawal_history(request):
    seller, err = _get_seller_or_error(request.user)
    if err:
        return err
    qs = seller.withdrawal_requests.order_by('-created_at')
    result = paginate_queryset(qs, request, WithdrawalRequestSerializer)
    return success_response(result)


# ═════════════════════════════════════════════════════════════════════
# SECTION 10 — ESCROW
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='GET',
    operation_id='escrow_entries',
    operation_summary='List seller escrow entries',
    operation_description=(
        'Returns paginated escrow entries for the seller. '
        'Escrow holds seller earnings until the buyer confirms delivery.\n\n'
        '**Status:** `holding` (locked) | `released` (moved to wallet) | `refunded` (cancelled order)\n\n'
        '**Filter:** `?status=holding|released|refunded`'
    ),
    tags=['Wallet'],
    manual_parameters= _pagination_params + [
        openapi.Parameter('status', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          description='holding | released | refunded'),
    ],
    responses={200: _success, 401: _error_401, 403: _error_403},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def escrow_entries(request):
    seller, err = _get_seller_or_error(request.user)
    if err:
        return err
    qs = seller.escrow_entries.select_related('order', 'order_item').order_by('-held_at')
    if request.query_params.get('status'):
        qs = qs.filter(status=request.query_params['status'])
    result = paginate_queryset(qs, request, EscrowEntrySerializer)
    return success_response(result)


# ═════════════════════════════════════════════════════════════════════
# SECTION 11 — REVIEWS
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='POST',
    operation_id='submit_product_review',
    operation_summary='Submit a product review',
    operation_description=(
        'Submits or updates a review for the given product. '
        'The `is_verified` flag is set only if the reviewer has a delivered order for the product. '
        'Automatically updates the product\'s aggregate rating and review count.\n\n'
        '**Body:** `{ "rating": 1-5, "comment": "..." (optional) }`'
    ),
    tags=['Reviews'],
    request_body=ProductReviewSerializer,
    responses={200: _success, 201: _success, 400: _error_400, 401: _error_401, 404: _error_404},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_product_review(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return error_response('Product not found.', 404)
    purchased = OrderItem.objects.filter(
        order__buyer=request.user, product=product, order__status='delivered',
    ).first()
    ser = ProductReviewSerializer(data=request.data)
    if not ser.is_valid():
        return error_response('Validation failed.', 400, errors=ser.errors)
    review, created = ProductReview.objects.update_or_create(
        product=product,
        buyer=request.user,
        defaults={
            'rating': ser.validated_data['rating'],
            'comment': ser.validated_data.get('comment', ''),
            'order_item': purchased,
            'is_verified': purchased is not None,
        },
    )
    avg = ProductReview.objects.filter(product=product).aggregate(avg=Avg('rating'))['avg'] or 0
    cnt = ProductReview.objects.filter(product=product).count()
    Product.objects.filter(id=product_id).update(rating=round(avg, 2), review_count=cnt)
    return success_response(
        ProductReviewSerializer(review).data,
        'Review submitted.' if created else 'Review updated.',
        201 if created else 200,
    )


# ═════════════════════════════════════════════════════════════════════
# SECTION 12 — NOTIFICATIONS
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='GET',
    operation_id='notifications_list',
    operation_summary='Get notifications',
    operation_description=(
        'Returns paginated notifications for the authenticated user. '
        'Types: `order_new`, `order_update`, `payment`, `escrow_release`, '
        '`review`, `message`, `system`, `product_approved`, `product_rejected`.\n\n'
        '**Filter:** `?unread=1` to return only unread notifications.'
    ),
    tags=['Notifications'],
    manual_parameters= _pagination_params + [
        openapi.Parameter('unread', openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                          description='Pass 1 to return only unread notifications'),
    ],
    responses={200: _success, 401: _error_401},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notifications_list(request):
    qs = request.user.notifications.order_by('-created_at')
    if request.query_params.get('unread') == '1':
        qs = qs.filter(is_read=False)
    result = paginate_queryset(qs, request, NotificationSerializer)
    return success_response(result)


@swagger_auto_schema(
    method='PUT',
    operation_id='mark_notification_read',
    operation_summary='Mark a single notification as read',
    operation_description='Sets `is_read=true` on a single notification belonging to the authenticated user.',
    tags=['Notifications'],
    responses={200: _success, 401: _error_401, 404: _error_404},
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, notification_id):
    try:
        n = Notification.objects.get(id=notification_id, user=request.user)
    except Notification.DoesNotExist:
        return error_response('Notification not found.', 404)
    n.is_read = True
    n.save(update_fields=['is_read'])
    return success_response(message='Marked as read.')


@swagger_auto_schema(
    method='PUT',
    operation_id='mark_all_notifications_read',
    operation_summary='Mark all notifications as read',
    operation_description='Sets `is_read=true` on all unread notifications for the authenticated user.',
    tags=['Notifications'],
    responses={200: _success, 401: _error_401},
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return success_response(message='All notifications marked as read.')


# ═════════════════════════════════════════════════════════════════════
# SECTION 13 — ADMIN UTILITIES
# ═════════════════════════════════════════════════════════════════════

@swagger_auto_schema(
    method='GET',
    operation_id='admin_dashboard_stats',
    operation_summary='[Admin] Dashboard statistics snapshot',
    operation_description=(
        'Returns key platform metrics:\n\n'
        '`total_products`, `pending_products`, `approved_products`, '
        '`total_orders`, `pending_orders`, `total_sellers`, '
        '`total_escrow` (funds currently held), `pending_withdrawals`.\n\n'
        '**Requires Django staff/admin status.**'
    ),
    tags=['Admin'],
    responses={200: _success, 401: _error_401},
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_dashboard_stats(request):
    from django.db.models import Sum
    stats = {
        'total_products':      Product.objects.count(),
        'pending_products':    Product.objects.filter(status='pending').count(),
        'approved_products':   Product.objects.filter(status='approved').count(),
        'total_orders':        Order.objects.count(),
        'pending_orders':      Order.objects.filter(status='pending').count(),
        'total_sellers':       SellerProfile.objects.filter(is_active=True).count(),
        'total_escrow':        float(EscrowEntry.objects.filter(status='holding')
                               .aggregate(total=Sum('amount'))['total'] or 0),
        'pending_withdrawals': WithdrawalRequest.objects.filter(status='pending').count(),
    }
    return success_response(stats)


@swagger_auto_schema(
    method='GET',
    operation_id='admin_withdrawal_requests',
    operation_summary='[Admin] List withdrawal requests',
    operation_description=(
        'Returns paginated withdrawal requests, defaulting to `status=pending`. '
        'Filter by `?status=pending|processing|completed|failed|cancelled`. '
        '**Requires Django staff/admin status.**'
    ),
    tags=['Admin'],
    manual_parameters= _pagination_params + [
        openapi.Parameter('status', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                          description='pending | processing | completed | failed | cancelled'),
    ],
    responses={200: _success, 401: _error_401},
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_withdrawal_requests(request):
    status_filter = request.query_params.get('status', 'pending')
    qs = WithdrawalRequest.objects.filter(status=status_filter).select_related('seller').order_by('-created_at')
    result = paginate_queryset(qs, request, WithdrawalRequestSerializer)
    return success_response(result)


@swagger_auto_schema(
    method='PUT',
    operation_id='admin_process_withdrawal',
    operation_summary='[Admin] Process a withdrawal request',
    operation_description=(
        'Marks a withdrawal as `completed` or `failed`.\n\n'
        '`completed` — confirms payment was made. Seller receives a success notification.\n\n'
        '`failed` — automatically refunds the amount to the seller\'s available balance '
        'and notifies them.\n\n'
        '**Body:** `status` (required), `admin_note` (optional), `external_ref` (optional)\n\n'
        '**Requires Django staff/admin status.**'
    ),
    tags=['Admin'],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['status'],
        properties={
            'status':       openapi.Schema(type=openapi.TYPE_STRING, enum=['completed', 'failed']),
            'admin_note':   openapi.Schema(type=openapi.TYPE_STRING),
            'external_ref': openapi.Schema(type=openapi.TYPE_STRING),
        },
    ),
    responses={200: _success, 400: _error_400, 401: _error_401, 404: _error_404},
)
@api_view(['PUT'])
@permission_classes([IsAdminUser])
def admin_process_withdrawal(request, withdrawal_id):
    try:
        w = WithdrawalRequest.objects.get(id=withdrawal_id)
    except WithdrawalRequest.DoesNotExist:
        return error_response('Withdrawal not found.', 404)
    new_status = request.data.get('status')
    if new_status not in ('completed', 'failed'):
        return error_response('Status must be "completed" or "failed".', 400)
    w.status = new_status
    w.admin_note = request.data.get('admin_note', w.admin_note)
    w.external_ref = request.data.get('external_ref', w.external_ref)
    w.processed_at = timezone.now()
    w.save()
    if new_status == 'failed':
        wallet = get_or_create_wallet(w.seller)
        wallet.available_balance += w.amount
        wallet.total_withdrawn -= w.amount
        wallet.save(update_fields=['available_balance', 'total_withdrawn'])
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='credit',
            category='adjustment',
            amount=w.amount,
            description='Withdrawal failed — amount refunded to wallet.',
            reference_id=str(w.id),
        )
        send_notification(
            user=w.seller.user,
            notification_type='payment',
            title='Withdrawal Failed',
            body=f'Your withdrawal of ₦{w.amount} failed and has been refunded.',
            data={'withdrawal_id': str(w.id)},
        )
    else:
        send_notification(
            user=w.seller.user,
            notification_type='payment',
            title='Withdrawal Successful',
            body=f'Your withdrawal of ₦{w.amount} has been processed.',
            data={'withdrawal_id': str(w.id)},
        )
    return success_response(message=f'Withdrawal {new_status}.')

