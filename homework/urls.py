from django.urls import path
from . import views

urlpatterns = [
    path('<int:homework_id>/', views.homework_detail, name='homework_detail'),
    path('<int:homework_id>/submit/', views.submit_homework, name='submit_homework'),
]