from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from users.views import CustomTokenView, register_view, logout_view, DoctorViewSet, admin_add_personnel, UserViewSet, google_auth_view
from appointments.views import AppointmentViewSet, verify_slip_view


# API router for automatic ViewSet URL routing
router = DefaultRouter()
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'doctors', DoctorViewSet, basename='doctor') 
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication endpoints
    path('api/login/', CustomTokenView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/google-auth/', google_auth_view, name='google_auth'),

    # User authentication actions
    path('api/register/', register_view, name='register'),
    path('api/logout/', logout_view, name='logout'),
    path('api/admin/add-personnel/', admin_add_personnel, name='admin_add_personnel'),

     # API routes for appointments and doctors
    path('api/', include(router.urls)),

    path('verify-slip/<int:appointment_id>/', verify_slip_view, name='verify_slip'),
]
