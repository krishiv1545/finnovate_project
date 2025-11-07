from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from core_APP.models import CustomUser, ResponsibilityMatrix


class AddTeamMemberForm(forms.Form):
    ROLE_CHOICES = (
        ("4", "Preparer"),
        ("5", "Reviewer"),
    )

    user = forms.ModelChoiceField(
        queryset=CustomUser.objects.filter(user_type=4),
        label="Select User",
        help_text="Choose a user to add to your team.",
    )
    user_role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        label="Assign Role",
        help_text="Select Preparer/Maker or Reviewer role.",
    )


@login_required
def team_management_view(request):
    # Only allow Department Heads (user_type 2) to access
    if getattr(request.user, "user_type", None) != 2:
        return HttpResponseForbidden("You do not have permission to access this page.")

    # Get the current user's department from their ResponsibilityMatrix entry
    try:
        user_responsibility = ResponsibilityMatrix.objects.filter(
            user=request.user, user_role=2
        ).first()
        if not user_responsibility or not user_responsibility.department:
            messages.error(
                request,
                "You are not assigned to a department. Please contact an administrator.",
            )
            return redirect("dashboard_page")
        department = user_responsibility.department
    except Exception:
        messages.error(
            request,
            "Unable to retrieve your department information. Please contact an administrator.",
        )
        return redirect("dashboard_page")

    # Get unique team members from ResponsibilityMatrix for this department
    # Get all responsibility entries, then get unique users
    responsibility_entries = ResponsibilityMatrix.objects.filter(
        department=department
    ).exclude(user=request.user).select_related("user")
    
    # Get unique user IDs
    unique_user_ids = responsibility_entries.values_list("user_id", flat=True).distinct()
    
    # Get the users and annotate with their role from ResponsibilityMatrix
    team_members = []
    for user_id in unique_user_ids:
        # Get the first responsibility entry for this user to get role info
        resp_entry = responsibility_entries.filter(user_id=user_id).first()
        if resp_entry:
            team_members.append({
                'user': resp_entry.user,
                'user_role': resp_entry.get_user_role_display(),
                'user_role_code': resp_entry.user_role,
            })
    
    # Sort by name
    team_members.sort(key=lambda x: (x['user'].first_name or '', x['user'].last_name or ''))

    # Get available users (user_type 4) that are not already in the team
    existing_user_ids = [member['user'].id for member in team_members]
    available_users = CustomUser.objects.filter(user_type=4).exclude(
        id__in=existing_user_ids
    )
    
    # Handle search query for available users
    search_query = request.GET.get("search", "").strip()
    if search_query:
        available_users = available_users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    if request.method == "POST":
        form = AddTeamMemberForm(request.POST)
        # Update queryset to only show available users
        form.fields["user"].queryset = available_users

        if form.is_valid():
            selected_user = form.cleaned_data["user"]
            user_role = int(form.cleaned_data["user_role"])

            try:
                with transaction.atomic():
                    ResponsibilityMatrix.objects.create(
                        user=selected_user,
                        department=department,
                        user_role=user_role,
                        gl_code=None,
                        gl_code_status=None,
                    )

                messages.success(
                    request,
                    f"User '{selected_user.get_full_name() or selected_user.username}' added to team successfully.",
                )
                return redirect("team_management_page")
            except IntegrityError:
                form.add_error(
                    None, "Unable to add user to team. They may already be in the team."
                )
        else:
            messages.error(request, "Please correct the errors below and resubmit.")
    else:
        form = AddTeamMemberForm()
        form.fields["user"].queryset = available_users

    context = {
        "form": form,
        "team_members": team_members,
        "department": department,
        "available_users": available_users,
        "search_query": search_query,
    }
    return render(request, "team_management/team_management.html", context)
