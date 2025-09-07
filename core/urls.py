from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
]

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('operations/', views.operations_list, name='operations'),
]

