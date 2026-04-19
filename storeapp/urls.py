# marketplace/urls.py

from django.urls import path

from storeapp import chat_views
from . import views

urlpatterns = [

    # ─────────────────────────────────────────────────────────────────
    # CATEGORIES
    # ─────────────────────────────────────────────────────────────────
    path('categories/', views.category_list, name='category-list'),
    path('categories/<slug:slug>/', views.category_detail, name='category-detail'),

    # ─────────────────────────────────────────────────────────────────
    # PRODUCT FEEDS  (buyer-facing)
    # ─────────────────────────────────────────────────────────────────
    path('products/hot-deals/', views.hot_deals, name='hot-deals'),
    path('products/just-for-you/', views.just_for_you, name='just-for-you'),
    path('products/explore/', views.explore, name='explore'),
    path('products/search/', views.search_products, name='product-search'),
    path('products/recommended/', views.recommended_products, name='recommended-no-id'),
    path('products/recommended/<str:product_id>/', views.recommended_products, name='recommended'),
    path('products/<str:product_id>/', views.product_detail, name='product-detail'),
    path('products/<str:product_id>/reviews/', views.product_reviews, name='product-reviews'),
    path('products/<str:product_id>/reviews/submit/', views.submit_product_review, name='submit-review'),

    # ─────────────────────────────────────────────────────────────────
    # SELLERS  (public profile)
    # ─────────────────────────────────────────────────────────────────
    path('sellers/<uuid:seller_id>/', views.seller_public_profile, name='seller-public-profile'),

    # ─────────────────────────────────────────────────────────────────
    # CATALOG  (admin-managed product templates)
    # ─────────────────────────────────────────────────────────────────
    path('catalog/products/', views.catalog_products, name='catalog-products'),
    path('catalog/products/<str:product_id>/', views.catalog_product_detail, name='catalog-product-detail'),

    # ─────────────────────────────────────────────────────────────────
    # SELLER — PROFILE & ONBOARDING
    # ─────────────────────────────────────────────────────────────────
    path('seller/onboard/', views.seller_onboard, name='seller-onboard'),
    path('seller/profile/', views.seller_profile, name='seller-profile'),
    path('seller/commission-rate/', views.commission_rate, name='commission-rate'),

    # ─────────────────────────────────────────────────────────────────
    # SELLER — LISTINGS
    # ─────────────────────────────────────────────────────────────────
    path('seller/listings/', views.seller_listings, name='seller-listings'),
    path('seller/listings/<str:product_id>/', views.seller_listing_detail, name='seller-listing-detail'),
    path('seller/listings/<str:product_id>/media/<uuid:media_id>/', views.delete_product_media, name='delete-product-media'),

    # ─────────────────────────────────────────────────────────────────
    # SELLER — ORDERS
    # ─────────────────────────────────────────────────────────────────
    path('seller/orders/', views.seller_orders, name='seller-orders'),
    path('seller/orders/<uuid:order_id>/status/', views.seller_update_order_status, name='seller-update-order-status'),

    # ─────────────────────────────────────────────────────────────────
    # CART
    # ─────────────────────────────────────────────────────────────────
    path('cart/', views.cart_detail, name='cart-detail'),
    path('cart/confirm-prices/', views.cart_confirm_prices, name='cart-confirm-prices'),

    # ─────────────────────────────────────────────────────────────────
    # BUYER ORDERS
    # ─────────────────────────────────────────────────────────────────
    path('orders/', views.orders, name='orders'),
    path('orders/<uuid:order_id>/', views.order_detail, name='order-detail'),
    path('orders/<uuid:order_id>/status/', views.update_order_status, name='update-order-status'),

    # ─────────────────────────────────────────────────────────────────
    # WALLET
    # ─────────────────────────────────────────────────────────────────
    path('wallet/', views.wallet_detail, name='wallet-detail'),
    path('wallet/sync/', views.wallet_sync, name='wallet-sync'),
    path('wallet/transactions/', views.wallet_transactions, name='wallet-transactions'),
    path('wallet/escrow/', views.escrow_entries, name='escrow-entries'),
    path('wallet/withdraw/', views.request_withdrawal, name='request-withdrawal'),
    path('wallet/withdrawals/', views.withdrawal_history, name='withdrawal-history'),

    # ─────────────────────────────────────────────────────────────────
    # NOTIFICATIONS
    # ─────────────────────────────────────────────────────────────────
    path('notifications/', views.notifications_list, name='notifications-list'),
    path('notifications/read-all/', views.mark_all_notifications_read, name='notifications-read-all'),
    path('notifications/<uuid:notification_id>/read/', views.mark_notification_read, name='notification-read'),

    # ─────────────────────────────────────────────────────────────────
    # ADMIN
    # ─────────────────────────────────────────────────────────────────
    path('admin/stats/', views.admin_dashboard_stats, name='admin-stats'),
    path('admin/products/', views.admin_products, name='admin-products'),
    path('admin/products/<str:product_id>/approve/', views.admin_approve_product, name='admin-approve-product'),
    path('admin/products/<str:product_id>/reject/', views.admin_reject_product, name='admin-reject-product'),
    path('admin/products/<str:product_id>/flags/', views.admin_update_product_flags, name='admin-product-flags'),
    path('admin/withdrawals/', views.admin_withdrawal_requests, name='admin-withdrawals'),
    path('admin/withdrawals/<uuid:withdrawal_id>/process/', views.admin_process_withdrawal, name='admin-process-withdrawal'),
    
    
    # business verification
    path('seller/verify-business/',        views.submit_business_verification, name='seller-verify-business'),
    path('seller/verify-business/status/', views.business_verification_status,  name='seller-verify-business-status'),
    
    # GET  → list all conversations for the logged-in user
    path('conversations/',chat_views.list_conversations,name='chat-list-conversations',),
 
    # POST → start a new conversation (or reuse existing) and send first message
    path('conversations/start/',chat_views.start_conversation,name='chat-start-conversation',),
 
    # GET  → fetch all messages (marks them read)
    # POST → send a new message
    # Both handled by conversation_messages() which dispatches on request.method
    path('conversations/<uuid:conversation_id>/messages/',chat_views.conversation_messages,name='chat-conversation-messages',),
 
    # DELETE → remove a conversation
    path('conversations/<uuid:conversation_id>/',chat_views.delete_conversation,name='chat-delete-conversation',),
]