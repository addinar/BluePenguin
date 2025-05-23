#  configure all our different urls so we can link them up and go to correct routes
from django.contrib import admin
from django.urls import path, include
from api.views import *
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView # access and refresh tokens prebuilt

# api/accounts/register lets you register
# api/accounts/<pk>/update-account-settings lets you update account settings (except shipping and payment details)
# api/accounts/<pk>/set-shipping-address lets you set shipping address
# api/accounts/<pk>/set-card-details lets you update set details
# api/accounts/<pk>/set-paypal-details lets you set paypal details
# api/profiles/<pk>/ lets you view profile
# api/profiles/<pk>/edit-profile lets you edit profile


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
]

'''
    path('admin/', admin.site.urls),
    path("api/", include("api.urls")), # when we go to smth api/, we take the reminder of that path and forward to api.urls
    path("api/user/register/", CreateUserView.as_view(), name="register"), # when we go to this route, call the view we created and make new user
    path("api/token/", TokenObtainPairView.as_view(), name="get_token"), # linked TokenObtainPairView view
    path("api/token/refresh/", TokenRefreshView.as_view(), name="refresh"), # linked TokenRefreshView view
    path("api-auth/", include("rest_framework.urls")), # linked all of the prebuilt urls we need from rest framework
    path('api/accounts/accept-win/', AccountViewSet.as_view({'post': 'accept_win'}), name='accept-win'),
'''