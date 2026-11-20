from django.urls import path
from django.views.generic import TemplateView
from planner.views import route_plan

urlpatterns = [path('api/route-plan/', route_plan), path('', TemplateView.as_view(template_name='map.html'))]
