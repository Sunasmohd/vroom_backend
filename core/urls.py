from django.urls import path
from .views import *

urlpatterns = [
    path('send-otp',send_otp),
    path('verify-otp',verify_otp),
    path('test-api',test_api),
    path('refresh',refresh_token_view),
    path('send-name',send_name_get_token),
    path('user/details/', get_user_details, name='get_user_details'),
    path('user/update/', update_user_details, name='update_user_details'),
    path('address/create/', create_user_address, name='address-create'),
    path('address/list/', get_all_addresses, name='address-list'),
    path('address/default/', get_default_address, name='address-default'),
    path('address/bulk-create/', bulk_create_user_addresses, name='address-bulk-create'),
    path('address/delete/<int:id>/', delete_user_address, name='address-delete'),
    path('address/update/<int:id>/', update_user_address, name='address-update'),
    path('address/set-default/', make_it_default, name='make_it_default'),
    path('feedback/submit/', submit_feedback, name='submit_feedback'),
    path('feedback/get/', get_user_feedback, name='get_user_feedback'),
]
