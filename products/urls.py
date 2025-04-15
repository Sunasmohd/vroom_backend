from django.urls import include, path
from .views import *
from rest_framework.routers import DefaultRouter

urlpatterns = [
    # Booking endpoints
    path('bookings/create/', create_booking, name='create_booking'), 
    path('bookings/', get_bookings, name='get_bookings'), 
    
    path('payments/add/', add_payment_method, name='add_payment_method'), 
    path('payments/process/', process_payment, name='process_payment'), 
    path('payments/methods/', get_payment_methods, name='get_payment_methods'), 
    
    path('refunds/check/', check_refund_amount, name='check_refund_amount'), 
    path('cancellations/create/', cancel_order_or_booking, name='cancel_order_or_booking'), 
    path('invoices/', get_invoices, name='get_invoices'), 
    
    #stripe payments
    path('create-payment-intent/', create_payment_intent, name='create_payment_intent'),
    path('get-payment-intent/', get_payment_intent, name='get_payment_intent'),
    path('get-charge-details/', get_charge_details, name='get_charge_details'),
    
    path('webhook/', stripe_webhook, name='stripe_webhook'),
    
    path('branch/', branch_list_view, name='branch_list_view'),
    path('branch/<int:branch_id>', branch_detail_view, name='branch_detail_view'),
    
    path('branch-status-bulk/', branch_status_bulk_view, name='branch_status_bulk_view'),
    
    path('branch-deals/<int:branch_id>', branch_deals_view, name='branch_deals_view'),
    path('branch-stock/<int:branch_id>', branch_stock_status_view, name='branch_stock_status_view'),
    path('branch-products/<int:branch_id>', branch_products_view, name='branch_products_view'),
    
    path('carousel-cards/', carousel_list_view, name='carousel_list_view'),
    path('offers/by-code/', get_offer_by_code, name='get_offer_by_code'),
    path('flash-sale-status/', get_flash_sale_status, name='get_flash_sale_status'),
    
    path('available-time-slots/', get_available_time_slots, name='get_available_time_slots'),
    
    # ... other paths ...
    path('favorites/', favorite_list_view, name='favorite_list'),
    path('favorites/create/', favorite_create_view, name='favorite_create'),
    path('favorites/<int:favorite_id>/delete/', favorite_delete_view, name='favorite_delete'),
    
    path('categories/', category_list_view, name='category_list_view'), 
    
    path('special-suggestions/', special_suggestions_list_view, name='special_suggestions_list_view'),  
    
    # Cart endpoints
    path('carts/', get_cart, name='get_cart'),  # Get user's cart
    
    path('carts/create/', create_cart, name='create_cart'),  # Create a new cart
    path('carts/<int:cart_id>/add-item/', add_item_to_cart, name='add_item_to_cart'),  # Add item to cart
    path('carts/<int:cart_id>/update-item/<int:item_id>', update_item_in_cart, name='update_item_to_cart'),  # Update item to cart
    path('carts/merge/', merge_cart, name='merge_cart'),  # Merge anonymous cart
    path('carts/<int:cart_id>/available-offers/', get_available_offers, name='get_available_offers'),
    path('carts/<int:cart_id>/apply-offer/', apply_offer, name='apply_offer'),
    path('carts/<int:cart_id>/remove-offer/', remove_offer, name='remove_offer'),
    path('carts/<int:cart_id>/items/<int:item_id>', update_cart_item_quantity, name='update_cart_item'),
    path('carts/<int:cart_id>/remove-item/<int:item_id>', remove_item_from_cart, name='remove_item_from_cart'),

    # Order endpoints
    path('orders/', get_orders, name='get_orders'),  # List user's orders
    path('orders/create/', create_order, name='create_order'),  # Create an order
    path('products/',product_list_view),
    path('products/<int:product_id>/',product_detail_view),
    path('menu/',menu_list_view),
    path('deal/',deal_list_view),
    path('deal/<int:deal_id>',deal_detail_view),
    path('dealcrt/',deal_create_view),
    
    
]
