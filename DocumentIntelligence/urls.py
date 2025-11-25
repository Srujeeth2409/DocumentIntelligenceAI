from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [

    path("", views.index, name="index"),
    path("ocr/", views.ocr_view, name="ocr"),
    path('classification/', views.classification, name='classification'),
    path('convert/', views.convert, name='convert'),
    path('generate-layout/', views.generate_layout, name='generate_layout'),
    #path('auth-model/', views.auth_model, name='auth_model'),
    #path('document-history/', views.document_history, name='document_history'),
    path('login/', views.login, name='login'),
    path('register/', views.register, name='register'),
    path('dashboard', views.dashboard, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),

]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)