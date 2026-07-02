from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from loginas.utils import restore_original_login


@login_required
@csrf_exempt
@require_POST
def stop_impersonating(request):
    restore_original_login(request)
    response = redirect("cadmin_course_list")
    return response
