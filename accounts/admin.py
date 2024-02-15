from django.contrib import admin
from unfold.admin import ModelAdmin
from django.contrib.auth.models import Group

# Register your models here.
from allauth.account.models import EmailAddress
from allauth.account.admin import EmailAddressAdmin
from allauth.socialaccount.models import SocialAccount, SocialToken, SocialApp
from allauth.socialaccount.admin import (
    SocialAccountAdmin,
    SocialTokenAdmin,
    SocialAppAdmin,
)
from django.contrib.sites.admin import SiteAdmin
from django.contrib.sites.models import Site

admin.site.unregister(Group)

@admin.register(Group)
class GroupAdmin(ModelAdmin):
    pass

admin.site.unregister(EmailAddress)

@admin.register(EmailAddress)
class EmailAddressAdmin(ModelAdmin):
    pass

admin.site.unregister(SocialAccount)

@admin.register(SocialAccount)
class SocialAccountAdmin(ModelAdmin):
    pass

admin.site.unregister(SocialToken)

@admin.register(SocialToken)
class SocialTokenAdmin(ModelAdmin):
    pass

admin.site.unregister(SocialApp)

@admin.register(SocialApp)
class SocialAppAdmin(ModelAdmin):
    pass

admin.site.unregister(Site)

@admin.register(Site)
class SiteAdmin(ModelAdmin):
    pass
