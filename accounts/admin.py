import secrets

from django import forms
from django.contrib import admin

from .models import CustomUser, Token


class CustomUserAdmin(admin.ModelAdmin):
    search_fields = ["email"]


admin.site.register(CustomUser, CustomUserAdmin)


class TokenAdminForm(forms.ModelForm):
    class Meta:
        model = Token
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(TokenAdminForm, self).__init__(*args, **kwargs)
        if not self.instance.pk:  # Check if this is a new object
            self.initial['key'] = secrets.token_urlsafe(16)


class TokenAdmin(admin.ModelAdmin):
    # autocomplete_fields = ['user']

    form = TokenAdminForm

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["queryset"] = CustomUser.objects.filter(
                is_staff=True
            )
            # Or use any condition to filter the queryset
            # based on permissions or other criteria
        return super().formfield_for_foreignkey(
            db_field, request, **kwargs
        )


admin.site.register(Token, TokenAdmin)
