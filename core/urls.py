# core/urls.py - REMPLACEZ le contenu par :
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('operations/', views.operations_list, name='operations_list'),
    path('operations/<int:operation_id>/', views.operation_detail, name='operation_detail'),
]