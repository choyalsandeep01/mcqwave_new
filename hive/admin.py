from django.contrib import admin

from hive.models import ConnectionRequest,Connection,Shared_Bookmark,Shared_Test
# Register your models here.
from django import forms
# Register your models here.
admin.site.register(ConnectionRequest)
admin.site.register(Connection)
admin.site.register(Shared_Bookmark)
admin.site.register(Shared_Test)