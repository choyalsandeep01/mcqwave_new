"""
URL configuration for myproject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from mcqs.views import plans,tnc,refund_policy,privacy_policy,contact,feedback,about_us
from accounts.views import submit_feedback,contact_submit
from django.views.static import serve
from django.urls import re_path
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('',include('accounts.urls')),
    path('home/',include('home.urls')),
    path('<email_token>/mcq/',include('mcqs.urls')),
    path('mcqs/', include('mcqs.urls')),
    path('pyqs/', include('pyqs.urls')),
    path('<email_token>/pyqs/', include('pyqs.urls')),
    path('<email_token>/pomegranate/', include('pomegranate.urls')),
    path('apipomegranate/', include('pomegranate.urls')),

    path('<email_token>/hive/', include('hive.urls')),
    path('hive/', include('hive.urls')),
    path('plans/', plans, name='plans'),
    path('t&c/', tnc, name='tnc'),
    path('refund-policy/', refund_policy, name='refund-policy'),
    path('privacy-policy/', privacy_policy, name='privacy_policy'),
    path('contact/', contact, name='contact'),
    path('feedback/', feedback, name='feedback'),
    path('about-us/', about_us, name='about-us'),
    path('submit-feedback/', submit_feedback, name='submit_feedback'),
    path('contact-submit/', contact_submit, name='contact_submit'),
    path('<email_token>/mocktest/', include('mocktest.urls')),
    path('mocktest/', include('mocktest.urls')),
    path('ads.txt', TemplateView.as_view(template_name="ads.txt", content_type='text/plain')),
    path('payment/', include('payments.urls')),
    path('flashcards/', include('flashcards.urls')),


    re_path(r'^media/(?P<path>.*)$', serve, {
        'document_root': settings.MEDIA_ROOT,
    }),

]
urlpatterns += staticfiles_urlpatterns()