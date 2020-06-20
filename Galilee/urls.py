
from django.contrib import admin
from django.urls import path, include, re_path
from rest_framework import routers
from infox import views as infox_views
from assist import views as assist_views
from vmmanage import views as vm_views

router = routers.DefaultRouter()
router.register('users', infox_views.UserViewSet, 'user')
router.register('groups', infox_views.GroupViewSet, 'groups')
router.register('userinfo', infox_views.UserinfoViewSet, 'userinfo')
router.register('orginfo', infox_views.OrginfoViewSet, 'orginfo')
router.register('assist', assist_views.AssistViewSet, 'assist')
router.register('vminfo', vm_views.VminfoViewSet, 'vminfo')
router.register('check_auth', infox_views.CheckAuthViewSet, 'check_auth')


urlpatterns = [
    path('admin/', admin.site.urls),
    re_path('api/(?P<version>(v1|v2))/', include(router.urls)),
    path('api/', infox_views.ApiInfoView.as_view()),
    # re_path('api/check_auth/', infox_views.CheckAuthView.as_view()),
    path('api_auth/', include('rest_framework.urls', namespace='rest_framework')),
]
