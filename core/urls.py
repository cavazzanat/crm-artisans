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
    path('clients/nouveau/', views.client_create, name='client_create'),
    path('clients/<int:client_id>/supprimer/', views.client_delete, name='client_delete'),
    path('clients/<int:client_id>/modifier/', views.client_edit, name='client_edit'),
    
    # Dans urls.py
    path('operations/<int:operation_id>/modifier/', views.operation_edit, name='operation_edit'),

    path('run-migration/', views.run_migration, name='run_migration'),

    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
    path('register/', views.register, name='register'),
]