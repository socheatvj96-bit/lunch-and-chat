from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmployeeViewSet, RestaurantViewSet, MenuItemViewSet, OrderViewSet
from . import web_views
from . import user_views

router = DefaultRouter()
router.register(r'employees', EmployeeViewSet)
router.register(r'restaurants', RestaurantViewSet)
router.register(r'menu-items', MenuItemViewSet)
router.register(r'orders', OrderViewSet)

urlpatterns = [
    # API endpoints
    path('api/', include(router.urls)),
    
    # Web interface
    path('', web_views.landing_page, name='landing'),
    path('contact-form/', web_views.contact_form_submit, name='contact_form_submit'),
    path('i_am_secret_file.csv', web_views.get_csv_file, name='csv_file'),
    path('catalog/', web_views.product_catalog, name='product_catalog'),
    path('login/', web_views.login_view, name='login'),
    path('logout/', web_views.logout_view, name='logout'),
    path('admin/products/', web_views.admin_products, name='admin_products'),
    path('admin/products/create/', web_views.create_product, name='create_product'),
    path('admin/products/<int:product_id>/update/', web_views.update_product, name='update_product'),
    path('admin/products/<int:product_id>/delete/', web_views.delete_product, name='delete_product'),
    path('admin/products/<int:product_id>/details/', web_views.get_product_details, name='get_product_details'),
    path('admin/images/<int:image_id>/delete/', web_views.delete_image, name='delete_image'),
    path('admin/images/<int:image_id>/set-primary/', web_views.set_primary_image, name='set_primary_image'),
    
    # User mini-app
    path('app/', user_views.user_app, name='user_app'),
    path('app/login/', user_views.user_login, name='user_login'),
    path('app/register/', user_views.user_register, name='user_register'),
    path('app/check-auth/', user_views.check_auth, name='check_auth'),
    path('app/menu/', user_views.get_menu, name='get_menu'),
    path('app/menu/week/', user_views.get_week_menu, name='get_week_menu'),
    path('app/order/', user_views.create_order, name='create_order'),
    path('app/employee/<int:employee_id>/', user_views.get_employee_info, name='get_employee_info'),
    path('app/employee/<int:employee_id>/orders/', user_views.get_employee_orders, name='get_employee_orders'),
    path('app/order/<int:order_id>/', user_views.get_order_details, name='get_order_details'),
    path('app/order/cancel/', user_views.cancel_order, name='cancel_order'),
    path('app/order/set-paid/', user_views.set_order_paid_by_me, name='set_order_paid_by_me'),
    path('app/telegram/link/', user_views.link_telegram, name='link_telegram'),
    path('app/report-item/', user_views.report_item, name='report_item'),
    path('app/settings/', user_views.get_settings, name='get_settings'),
    path('app/employees/', user_views.get_employees_list, name='get_employees_list'),
    path('app/support/', user_views.send_support_message, name='send_support_message'),
    path('app/telegram/link-token/', user_views.telegram_link_token, name='telegram_link_token'),
    path('app/push/subscribe/', user_views.push_subscribe, name='push_subscribe'),
    path('app/push/send/', user_views.push_send, name='push_send'),
    path('app/push/test/', user_views.push_send_test, name='push_send_test'),
    path('app/upload-avatar/', user_views.upload_avatar, name='upload_avatar'),
    path('api/integration/menu/day/', user_views.api_available_menu_day, name='api_available_menu_day'),
    path('api/integration/menu/images/upload/', user_views.api_upload_item_images, name='api_upload_item_images'),
    
    # New utility endpoints
    path('spora/', web_views.spora_instruction, name='spora_instruction'),
    path('backup-db/', web_views.backup_database, name='backup_database'),
    path('secret/svodka/', web_views.svodka_page, name='svodka'),
    path('secret/svodka-mob/', web_views.svodka_mob_page, name='svodka_mob'),
    path('secret/svodka-mob2/', web_views.svodka_mob2_page, name='svodka_mob2'),
    path('secret/svodka-mob2/help/', web_views.svodka_mob2_help_page, name='svodka_mob2_help'),
]

