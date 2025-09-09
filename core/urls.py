from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('operations/', views.operations_list, name='operations'),
    path('operations/nouvelle/', views.operation_create, name='operation_create'),
    path('operations/<int:operation_id>/', views.operation_detail, name='operation_detail'),
    path('operations/<int:operation_id>/duplicate/', views.operation_duplicate, name='operation_duplicate'),
    path('clients/', views.clients_list, name='clients'),
    path('clients/<int:client_id>/', views.client_detail, name='client_detail'),
    path('test-logout/', views.test_logout, name='test_logout'),  # Nouvelle ligne
]