from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from django.views.decorators.http import require_http_methods
import logging
from core_APP.models import BalanceSheet, ResponsibilityMatrix, TrialBalance, GLReview, GLSupportingDocument,   ReviewTrail
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from core_APP.models import GLReview
from django.http import JsonResponse


logger = logging.getLogger(__name__)


@login_required
def gl_reviews_view(request):
    """GL Reviews page - shows both Preparer and Reviewer GLs side by side or single FC/Head view."""

    # -------------------------------
    # USER TYPE 4: Preparer/Reviewer
    # -------------------------------
    if request.user.user_type == 4:
        # Get Preparer GLs (user_role = 4)
        preparer_assignments = ResponsibilityMatrix.objects.filter(
            user=request.user,
            gl_code__isnull=False,
            user_role=4
        ).select_related('department').order_by('gl_code')

        # Get Reviewer GLs (user_role = 5)
        reviewer_assignments = ResponsibilityMatrix.objects.filter(
            user=request.user,
            gl_code__isnull=False,
            user_role=5
        ).select_related('department').order_by('gl_code')

        def prepare_gl_data(assignments, is_preparer=False):
            """Helper to prepare GL data with linked reviews and documents."""
            gl_data = []
            for assignment in assignments:
                balance_sheet = BalanceSheet.objects.filter(gl_acct=assignment.gl_code).first()

                if is_preparer:
                    trial_balance = TrialBalance.objects.filter(
                        user=request.user,
                        gl_code=assignment.gl_code
                    ).first()
                else:
                    trial_balance = TrialBalance.objects.filter(gl_code=assignment.gl_code).first()

                gl_review = None
                supporting_docs = []
                if trial_balance:
                    if is_preparer:
                        gl_review = GLReview.objects.filter(
                            trial_balance=trial_balance,
                            reviewer=request.user
                        ).first()
                    else:
                        gl_review = GLReview.objects.filter(trial_balance=trial_balance).first()

                    if gl_review:
                        supporting_docs = GLSupportingDocument.objects.filter(
                            gl_review=gl_review
                        ).order_by('-uploaded_at')

                status_code = assignment.gl_code_status or 1
                status_display = assignment.get_gl_code_status_display() if assignment.gl_code_status else 'Pending'

                if gl_review:
                    status_code = gl_review.status
                    status_display = gl_review.get_status_display()

                assigned_on = assignment.created_at
                assigned_on_formatted = assigned_on.strftime("%B %d, %Y at %I:%M %p") if assigned_on else 'N/A'

                gl_code = assignment.gl_code
                trial_bal_field = TrialBalance.objects.filter(gl_code=gl_code).first()
                gl_rev = GLReview.objects.filter(trial_balance=trial_bal_field).first()

                gl_data.append({
                    'assignment_id': str(assignment.id),
                    'gl_code': assignment.gl_code,
                    'gl_name': balance_sheet.gl_account_name if balance_sheet else 'N/A',
                    'department': assignment.department.name if assignment.department else 'N/A',
                    'user_role': assignment.get_user_role_display(),
                    'status': status_display,
                    'status_code': status_code,
                    'assigned_on': assigned_on_formatted,
                    'assigned_on_datetime': assigned_on,
                    'reconciliation_notes': gl_rev.reconciliation_notes if gl_review else 'N/A',
                    'trial_balance_id': str(trial_balance.id) if trial_balance else None,
                    'gl_review_id': str(gl_review.id) if gl_review else None,
                    'supporting_documents': [
                        {
                            'id': str(doc.id),
                            'file_name': doc.file.name.split('/')[-1] if doc.file else 'Unknown',
                            'file_url': doc.file.url if doc.file else '#',
                            'uploaded_at': doc.uploaded_at.strftime("%B %d, %Y at %I:%M %p") if doc.uploaded_at else 'N/A',
                        }
                        for doc in supporting_docs
                    ],
                })
            return gl_data

        preparer_gls = prepare_gl_data(preparer_assignments, is_preparer=True)
        reviewer_gls = prepare_gl_data(reviewer_assignments, is_preparer=False)

        return render(
            request,
            'gl_reviews/gl_reviews_t3.html',
            {'preparer_gls': preparer_gls, 'reviewer_gls': reviewer_gls}
        )

    # -------------------------------
    # USER TYPE 2 or 3: FC / Department Head
    # -------------------------------
    if request.user.user_type in [2, 3]:
        # Fetch all GLReviews assigned to this reviewer
        gl_reviews_qs = GLReview.objects.filter(
            reviewer=request.user
        ).select_related('trial_balance', 'trial_balance__user').order_by('-reviewed_at')

        gl_reviews = []
        for review in gl_reviews_qs:
            trial_balance = review.trial_balance
            assignment = ResponsibilityMatrix.objects.filter(
                gl_code=trial_balance.gl_code
            ).select_related('department').first()

            balance_sheet = BalanceSheet.objects.filter(
                gl_acct=trial_balance.gl_code
            ).first()

            supporting_docs = GLSupportingDocument.objects.filter(
                gl_review=review
            ).order_by('-uploaded_at')

            assigned_on = assignment.created_at if assignment else None
            assigned_on_formatted = assigned_on.strftime("%B %d, %Y at %I:%M %p") if assigned_on else 'N/A'
            print("ASSIGNMENT ID: ", str(assignment.id) if assignment else None)
            gl_reviews.append({
                'assignment_id': str(assignment.id) if assignment else None,
                'gl_code': trial_balance.gl_code,
                'gl_name': balance_sheet.gl_account_name if balance_sheet else 'N/A',
                'department': assignment.department.name if assignment and assignment.department else 'N/A',
                'status': review.get_status_display(),
                'status_code': review.status,
                'assigned_on': assigned_on_formatted,
                "reconciliation_notes": review.reconciliation_notes,
                'supporting_documents': [
                    {
                        'id': str(doc.id),
                        'file_name': doc.file.name.split('/')[-1] if doc.file else 'Unknown',
                        'file_url': doc.file.url if doc.file else '#',
                        'uploaded_at': doc.uploaded_at.strftime("%B %d, %Y at %I:%M %p") if doc.uploaded_at else 'N/A',
                    }
                    for doc in supporting_docs
                ],
            })

        print(f"[INFO] {request.user} — GL Reviews fetched: {len(gl_reviews)}")

        return render(request, 'gl_reviews/gl_reviews_t2.html', {'gl_reviews': gl_reviews})


@login_required
def remove_gl_supporting_document(request, document_id):
    if request.method != 'POST':
        logger.error(request, "Invalid request method.")
        return redirect("gl_reviews_page")
    
    try:
        document = GLSupportingDocument.objects.get(id=document_id)
        document.delete()
        messages.success(request, "Document removed successfully.")
    except GLSupportingDocument.DoesNotExist:
        logger.error(request, "Document not found.")
    
    return redirect("gl_reviews_page")


@login_required
def upload_gl_supporting_document(request):
    """Upload a supporting document for a GL review (Preparer only)."""
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect("gl_reviews_page")
    
    if request.user.user_type != 4:
        messages.error(request, "You do not have permission to upload documents.")
        return redirect("gl_reviews_page")
    
    assignment_id = request.POST.get('assignment_id')
    gl_code = request.POST.get('gl_code')
    uploaded_file = request.FILES.get('supporting_document')
    
    if not assignment_id or not gl_code or not uploaded_file:
        messages.error(request, "Missing required information.")
        return redirect("gl_reviews_page")
    
    try:
        # Verify the assignment belongs to the user and is Preparer role
        assignment = ResponsibilityMatrix.objects.get(
            id=assignment_id,
            user=request.user,
            gl_code=gl_code,
            user_role=4  # Preparer only
        )
        
        # Get or create TrialBalance
        trial_balance = TrialBalance.objects.filter(
            user=request.user,
            gl_code=gl_code
        ).first()
        
        if not trial_balance:
            balance_sheet = BalanceSheet.objects.filter(gl_acct=gl_code).first()
            trial_balance = TrialBalance.objects.create(
                user=request.user,
                gl_code=gl_code,
                gl_name=balance_sheet.gl_account_name if balance_sheet else '',
                amount=0,
            )
        
        # Get or create GLReview
        gl_review = GLReview.objects.filter(
            trial_balance=trial_balance,
            reviewer=request.user
        ).first()
        
        if not gl_review:
            gl_review = GLReview.objects.create(
                trial_balance=trial_balance,
                reviewer=request.user,
                reconciliation_notes='',
                status=1,  # Pending
            )
        
        # Create GLSupportingDocument
        with transaction.atomic():
            GLSupportingDocument.objects.create(
                gl_review=gl_review,
                file=uploaded_file,
            )
        
        messages.success(request, f"Supporting document uploaded successfully for GL Code {gl_code}.")
        
    except ResponsibilityMatrix.DoesNotExist:
        messages.error(request, "GL assignment not found or you don't have permission to upload documents for this GL.")
    except Exception as e:
        messages.error(request, f"Error uploading document: {str(e)}")
    
    return redirect("gl_reviews_page")


@login_required
@require_http_methods(["POST"])
def submit_gl_review_preparer(request):
    """
    Submit a GL review for an assigned GL code.
    """
    
    assignment_id = request.POST.get('assignment_id')
    gl_code = request.POST.get('gl_code')
    reconciliation_notes = request.POST.get('reconciliation_notes', '').strip()
    
    if not assignment_id or not gl_code:
        messages.error(request, "Missing required information.")
        return redirect("gl_reviews_page")
    
    if not reconciliation_notes:
        messages.error(request, "Reconciliation notes are required.")
        return redirect("gl_reviews_page")
    
    try:
        # Verify the assignment belongs to the user
        assignment = ResponsibilityMatrix.objects.get(
            id=assignment_id,
            gl_code=gl_code
        )
        
        # Find or create a TrialBalance entry for this GL code
        # We need to link GLReview to TrialBalance, so we'll find or create one
        trial_balance = TrialBalance.objects.filter(
            gl_code=gl_code
        ).first()
        
        # If no TrialBalance exists, create one (minimal entry)
        if not trial_balance:
            trial_balance = TrialBalance.objects.create(
                user=request.user,
                gl_code=gl_code,
                gl_name=BalanceSheet.objects.filter(gl_acct=gl_code).values_list('gl_account_name', flat=True).first() or '',
                amount=0,
            )
        
        # Create or update GLReview
        with transaction.atomic():
            # Check if review already exists
            gl_review = GLReview.objects.filter(
                trial_balance=trial_balance,
                reviewer=request.user
            ).first()
            
            if gl_review:
                # Update existing review
                gl_review.reconciliation_notes = reconciliation_notes
                gl_review.status = 2  # Awaiting Approval
                gl_review.save()
            else:
                # Create new review
                gl_review = GLReview.objects.create(
                    trial_balance=trial_balance,
                    reviewer=request.user,
                    reconciliation_notes=reconciliation_notes,
                    status=2,  # Awaiting Approval
                )
            
            # Update ResponsibilityMatrix status
            assignment.gl_code_status = 2  # Done
            assignment.save()

            # Also mark in ReviewTrail
            review_trail = ReviewTrail.objects.create(
                reviewer=request.user,
                reviewer_responsibility_matrix=assignment,
                gl_review=gl_review,
                previous_trail=None,
                gl_code=gl_code,
                gl_name=BalanceSheet.objects.filter(gl_acct=gl_code).values_list('gl_account_name', flat=True).first() or '',
                reconciliation_notes=reconciliation_notes,
                action='Submitted'
            )
            review_trail.save()
        
        messages.success(
            request,
            f"GL Review submitted successfully for GL Code {gl_code}. Status updated to 'Awaiting Approval'."
        )
        
    except ResponsibilityMatrix.DoesNotExist:
        messages.error(request, "GL assignment not found or does not belong to you.")
    except Exception as e:
        logger.error(f"Error submitting GL review: {str(e)}")
        messages.error(request, f"Error submitting review: {str(e)}")
    
    return redirect("gl_reviews_page")


@login_required
@require_http_methods(["POST"])
def submit_gl_review_reviewer(request):
    """
    Submit a GL review for an assigned GL code.
    """
    assignment_id = request.POST.get("assignment_id")
    gl_code = request.POST.get("gl_code")
    reconciliation_notes = request.POST.get("reconciliation_notes")
    action = request.POST.get("action")  # either 'approve' or 'reject'

    
    if not assignment_id or not gl_code:
        messages.error(request, "Missing required information.")
        return redirect("gl_reviews_page")
    
    if not reconciliation_notes:
        messages.error(request, "Reconciliation notes are required.")
        return redirect("gl_reviews_page")
    
    trial_balance = TrialBalance.objects.filter(
        gl_code=gl_code
    ).first()
    if not trial_balance:
        print("TRIAL BALANCE NOT FOUND")
        messages.error(request, "Trial balance not found.")
        return redirect("gl_reviews_page")
    print("FOUND TRIAL BALANCE:", trial_balance.id)
    
    gl_review = GLReview.objects.filter(
        trial_balance=trial_balance,
    ).first()

    if not gl_review:
        print("GL REVIEW NOT FOUND")
        messages.error(request, "GL review not found.")
        return redirect("gl_reviews_page")
    
    previous_trail = ReviewTrail.objects.filter(
        gl_review=gl_review
    ).order_by('-created_at').first()
    if not previous_trail:
        print("PREVIOUS TRAIL NOT FOUND")
        messages.error(request, "Previous trail not found.")
        return redirect("gl_reviews_page")
    print("FOUND PREVIOUS TRAIL:", previous_trail.id)
    
    assignment = ResponsibilityMatrix.objects.get(
        id=assignment_id,
        gl_code=gl_code
    )
    if action == 'approve':
        assignment.gl_code_status = 3  # Approved
        # get FC
        fc = ResponsibilityMatrix.objects.filter(
            user_role=3,
            department=assignment.department
        ).first()
        print("FC: ", fc.id)
    else:
        assignment.gl_code_status = 4  # Rejected

    assignment.save()
    
    gl_review.reconciliation_notes = reconciliation_notes
    if action == 'approve':
        # fc is responsibility mat
        gl_review.reviewer = fc.user
    else:
        gl_review.reviewer = previous_trail.reviewer
    gl_review.save()

    review_trail = ReviewTrail.objects.create(
        reviewer=request.user,
        reviewer_responsibility_matrix=assignment,
        gl_review=gl_review,
        previous_trail=previous_trail,
        reconciliation_notes=reconciliation_notes,
        gl_code=gl_code,
        action='Approved' if action == 'approve' else 'Rejected'
    )
    review_trail.save()

    messages.success(
        request,
        f"GL Review submitted successfully for GL Code {gl_code}. Status updated to '{assignment.gl_code_status}'."
    )

    if action == 'approve':
        # send mail to FC
        fc_email = fc.user.email
        send_mail(
            'GL Review Available',
            f'GL Review for GL Code {gl_code} is available for your approval.',
            settings.EMAIL_HOST_USER,
            [fc_email],
            fail_silently=False,
        )
    # find next
    else:
        # mail previous
        prev_reviewer = previous_trail.reviewer
        send_mail(
            'GL Review Rejected',
            f'Your GL Review for GL Code {gl_code} has been rejected.',
            settings.EMAIL_HOST_USER,
            [prev_reviewer.email],
            fail_silently=False,
        )

    return redirect("gl_reviews_page")


@login_required
def balance_sheet_view(request):
    """Detailed balance sheet view for Tier 3 navigation."""

    sheets = (
        BalanceSheet.objects
        .filter(user=request.user)
        .order_by('-added_at')
    )

    stats = {
        "total": sheets.count(),
        "open_items": sheets.filter(recon_status__iexact='open').count(),
        "flagged": sheets.exclude(flag_color__isnull=True).exclude(flag_color='').count(),
        "analysis_required": sheets.filter(analysis_required__iexact='yes').count(),
    }

    context = {
        "balance_sheets": sheets,
        "stats": stats,
    }
    return render(request, 'gl_reviews/balance_sheet.html', context)


@login_required
def get_review_trail(request, gl_code):
    """
    Fetch the review trail history for a specific GL code.
    Returns JSON data for the timeline.
    """
    trails = ReviewTrail.objects.filter(gl_code=gl_code).select_related('reviewer', 'previous_trail').order_by('created_at')
    
    trail_data = []
    
    # 0. Initial Assignment (Optional: fetch from ResponsibilityMatrix if needed, 
    # but trails usually start from first submission).
    # If trails are empty, we might want to show "Assigned" at least.
    
    # Let's iterate through recorded trails
    for trail in trails:
        trail_entry = {
            'id': str(trail.id),
            'reviewer': f"{trail.reviewer.first_name} {trail.reviewer.last_name} ({trail.reviewer.username})" if trail.reviewer else "Unknown",
            'role': 'Preparer' if trail.action == 'Submitted' else 'Reviewer', # Simplified inference
            'action': trail.action,
            'notes': trail.reconciliation_notes,
            'date': trail.created_at.strftime("%B %d, %Y"),
            'time': trail.created_at.strftime("%I:%M %p"),
            'timestamp': trail.created_at.isoformat(),
        }
        trail_data.append(trail_entry)
        
    return JsonResponse({'trails': trail_data})

