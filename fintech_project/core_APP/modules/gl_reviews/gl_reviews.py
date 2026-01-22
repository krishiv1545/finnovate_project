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

                # if gl_review:
                #    status_code = gl_review.status
                #    status_display = gl_review.get_status_display()

                assigned_on = assignment.created_at
                assigned_on_formatted = assigned_on.strftime("%B %d, %Y at %I:%M %p") if assigned_on else 'N/A'

                gl_code = assignment.gl_code
                trial_bal_field = TrialBalance.objects.filter(gl_code=gl_code).first()
                gl_rev = GLReview.objects.filter(trial_balance=trial_bal_field).first()

                preparer_assignment_status = None
                if not is_preparer:
                    # if reviewer, there has to be a preparer assignment
                    preparer_assignment = ResponsibilityMatrix.objects.filter(
                        gl_code=assignment.gl_code,
                        user_role=4
                    ).first()
                    if preparer_assignment:
                        preparer_assignment_status = preparer_assignment.gl_code_status

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
                    'preparer_assignment_status': preparer_assignment_status,
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
    # USER TYPE 2: Tower Head
    # -------------------------------
    if request.user.user_type == 2:
        # Init Tower Head ResponsibilityMatrix rows
        main_tower_assignment = ResponsibilityMatrix.objects.filter(
            user_role=2
        ).select_related('department').first()

        gl_reviews_qs = GLReview.objects.all().select_related('trial_balance', 'trial_balance__user').order_by('-reviewed_at')

        for review in gl_reviews_qs:
            trial_balance = review.trial_balance
            assignment = ResponsibilityMatrix.objects.filter(
                user=request.user,
                gl_code=trial_balance.gl_code
            )
            if not assignment.exists():
                if main_tower_assignment.gl_code:
                     # create new assignment
                     print("CREATING NEW TOWER ASSIGNMENT")
                     new_tower_assignment = ResponsibilityMatrix.objects.create(
                        user=request.user,
                        gl_code=trial_balance.gl_code,
                        gl_code_status=1,
                        department=main_tower_assignment.department,
                        user_role=2
                     )
                     new_tower_assignment.save()
                else:
                    print("MAIN TOWER HAS NO GL CODE, ASSIGNING TO SELF")
                    main_tower_assignment.gl_code = trial_balance.gl_code
                    main_tower_assignment.gl_code_status = 1
                    main_tower_assignment.save()

        # Get Tower Head Assignments
        tower_assignments = ResponsibilityMatrix.objects.filter(
            user=request.user,
            user_role=2,
            gl_code__isnull=False
        ).select_related('department').order_by('-created_at')

        gl_reviews = []

        for assignment in tower_assignments:
            trial_balance = TrialBalance.objects.filter(
                gl_code=assignment.gl_code
            ).first()

            gl_review = GLReview.objects.filter(
                trial_balance=trial_balance
            ).first() if trial_balance else None

            balance_sheet = BalanceSheet.objects.filter(
                gl_acct=assignment.gl_code
            ).first()

            supporting_docs = GLSupportingDocument.objects.filter(
                gl_review=gl_review
            ).order_by('-uploaded_at') if gl_review else []

            fc_assignment = ResponsibilityMatrix.objects.filter(
                gl_code=assignment.gl_code,
                user_role=3
            ).first()

            fc_status = fc_assignment.gl_code_status if fc_assignment else 1
            
            # Actionable if FC Status is 'Approved by FC' (5)
            is_actionable = (fc_status == 3)
            
            last_status_text = ""
            if gl_review.reviewer.user_type == 4:
                # could be preparer/reviewer
                print("GL CODE: ", assignment.gl_code)
                reviewer_assignment = ResponsibilityMatrix.objects.filter(
                    gl_code=trial_balance.gl_code,
                    user_role=5
                ).first()
                if reviewer_assignment:
                    if reviewer_assignment.gl_code_status == 4:
                        last_status_text = "GL Review-I (Preparer)"
                    else:
                        last_status_text = "GL Review-II (Reviewer)"
                else:
                    last_status_text = "GL Review-I (Preparer)"
            else:
                last_status_text = "GL Review-III (Finance Controller)"

            gl_reviews.append({
                'assignment_id': str(assignment.id),
                'gl_code': assignment.gl_code,
                'gl_name': balance_sheet.gl_account_name if balance_sheet else 'N/A',
                'department': assignment.department.name if assignment.department else 'N/A',
                'fc_status': fc_status,
                'status': last_status_text,
                'status_code': assignment.gl_code_status or 1,
                'assigned_on': assignment.created_at.strftime("%B %d, %Y at %I:%M %p"),
                'reconciliation_notes': gl_review.reconciliation_notes if gl_review else 'N/A',
                'supporting_documents': [
                    {
                        'id': str(doc.id),
                        'file_name': doc.file.name.split('/')[-1],
                        'file_url': doc.file.url,
                        'uploaded_at': doc.uploaded_at.strftime("%B %d, %Y at %I:%M %p"),
                    }
                    for doc in supporting_docs
                ],
                'is_actionable': is_actionable
            })
        
        def tower_sort_key(x):
            if x['is_actionable']:
                return 0
            if x['status_code'] in (7, 8):
                return 1
            return 2

        gl_reviews.sort(key=tower_sort_key)

        return render(request, 'gl_reviews/gl_reviews_t1.html', {'gl_reviews': gl_reviews})


    # -------------------------------
    # USER TYPE 3: FC
    # -------------------------------
    if request.user.user_type == 3:
        # Init UBFC ResponsibilityMatrix rows
        main_ubfc_assignment = ResponsibilityMatrix.objects.filter(
            user_role=3
        ).select_related('department').first()

        gl_reviews_qs = GLReview.objects.filter(
            reviewer=request.user
        ).select_related('trial_balance', 'trial_balance__user').order_by('-reviewed_at')

        for review in gl_reviews_qs:
            trial_balance = review.trial_balance
            assignment = ResponsibilityMatrix.objects.filter(
                user=request.user,
                gl_code=trial_balance.gl_code
            )
            if not assignment.exists():
                # there will always be a ubfc_assignment (blank one created early on)
                if main_ubfc_assignment.gl_code:
                    # create new assignment
                    print("CREATING NEW UBFC ASSIGNMENT")
                    new_ubfc_assignment = ResponsibilityMatrix.objects.create(
                        user=request.user,
                        gl_code=trial_balance.gl_code,
                        gl_code_status=1,
                        department=main_ubfc_assignment.department,
                        user_role=3
                    )
                    new_ubfc_assignment.save()
                else:
                    print("MAIN UBFC HAS NO GL CODE, ASSIGNING TO SELF")
                    main_ubfc_assignment.gl_code = trial_balance.gl_code
                    main_ubfc_assignment.gl_code_status = 1
                    main_ubfc_assignment.save()

            refetch_bufc_assignment = ResponsibilityMatrix.objects.filter(
                user=request.user,
                gl_code=trial_balance.gl_code
            ).first()
            reviewer_assignment = ResponsibilityMatrix.objects.filter(
                gl_code=trial_balance.gl_code,
                user_role=5
            ).first()
            if reviewer_assignment.gl_code_status == 3:
                refetch_bufc_assignment.gl_code_status = 1 # reset to pending after Reviewer approves the GL Review
                refetch_bufc_assignment.save()
            print(f"GL CODE: {trial_balance.gl_code}, BUFC STATUS: {refetch_bufc_assignment.gl_code_status}, REVIEWER STATUS: {reviewer_assignment.gl_code_status}")

        ubfc_assignments = ResponsibilityMatrix.objects.filter(
            user=request.user,
            gl_code__isnull=False
        ).select_related('department').order_by('-created_at')

        gl_reviews = []

        for assignment in ubfc_assignments:
            trial_balance = TrialBalance.objects.filter(
                gl_code=assignment.gl_code
            ).first()

            gl_review = GLReview.objects.filter(
                trial_balance=trial_balance
            ).first() if trial_balance else None

            balance_sheet = BalanceSheet.objects.filter(
                gl_acct=assignment.gl_code
            ).first()

            supporting_docs = GLSupportingDocument.objects.filter(
                gl_review=gl_review
            ).order_by('-uploaded_at') if gl_review else []

            reviewer_assignment = ResponsibilityMatrix.objects.filter(
                gl_code=assignment.gl_code,
                user_role=5
            ).first()

            gl_reviews.append({
                'assignment_id': str(assignment.id),
                'gl_code': assignment.gl_code,
                'gl_name': balance_sheet.gl_account_name if balance_sheet else 'N/A',
                'department': assignment.department.name if assignment.department else 'N/A',
                'reviewer_assignment_status': reviewer_assignment.gl_code_status if reviewer_assignment else None,
                'status': assignment.get_gl_code_status_display(),
                'status_code': assignment.gl_code_status or 1,
                'assigned_on': assignment.created_at.strftime("%B %d, %Y at %I:%M %p"),
                'reconciliation_notes': gl_review.reconciliation_notes if gl_review else 'N/A',
                'supporting_documents': [
                    {
                        'id': str(doc.id),
                        'file_name': doc.file.name.split('/')[-1],
                        'file_url': doc.file.url,
                        'uploaded_at': doc.uploaded_at.strftime("%B %d, %Y at %I:%M %p"),
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
            assignment.gl_code_status = 2  # Submitted
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
    preparer_assignment = ResponsibilityMatrix.objects.filter(
        gl_code=assignment.gl_code,
        user_role=4,
    ).first()
    if action == 'approve':
        assignment.gl_code_status = 3  # Approved
        # get FC
        fc = ResponsibilityMatrix.objects.filter(
            user_role=3,
            department=assignment.department
        ).first()
        print("FC: ", fc.id)
        preparer_assignment.gl_code_status = 3  # Approved
    else:
        assignment.gl_code_status = 4  # Rejected
        preparer_assignment.gl_code_status = 4  # Rejected

    assignment.save()
    preparer_assignment.save()
    
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

    # Update Previous Reviewer/Preparer Status on Rejection
    if action == 'reject':
        if previous_trail and previous_trail.reviewer_responsibility_matrix:
            prev_matrix = previous_trail.reviewer_responsibility_matrix
            prev_matrix.gl_code_status = 4 # Rejected
            prev_matrix.save()
            print(f"Updated Previous Matrix {prev_matrix.id} to Rejected")
        
        # Current reviewer status? Stay as Submitted or Pending?
        # If I rejected it, I am Submitted with it until it comes back.
        # But for now, let's leave my status as 'Rejected' (4) to indicate I pushed it back? 
        # Or 'Submitted' (2)? Existing code sets it to 4. 
        # "Only if Reviewer rejects, the status should affect him [Preparer]." - satisfied by prev_matrix update.


    messages.success(
        request,
        f"GL Review submitted successfully for GL Code {gl_code}. Status updated to '{assignment.get_gl_code_status_display()}'."
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
@require_http_methods(["POST"])
def submit_gl_review_bufc(request):
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
    reviewer_assignment = ResponsibilityMatrix.objects.filter(
        gl_code=assignment.gl_code,
        user_role=5,
    ).first()
    if action == 'approve':
        assignment.gl_code_status = 3  # Approved
        reviewer_assignment.gl_code_status = 5  # Approved by FC
    else:
        assignment.gl_code_status = 4  # Rejected
        reviewer_assignment.gl_code_status = 6  # Rejected by FC

    assignment.save()
    reviewer_assignment.save()

    dh = ResponsibilityMatrix.objects.filter(
        user_role=2,
        department=assignment.department
    ).first()
    print("Dept. Head (DH): ", dh.id)
    
    gl_review.reconciliation_notes = reconciliation_notes
    if action == 'approve':      
        gl_review.reviewer = dh.user
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

    # Update Previous Reviewer/Preparer Status on Rejection
    if action == 'reject':
        if previous_trail and previous_trail.reviewer_responsibility_matrix:
            prev_matrix = previous_trail.reviewer_responsibility_matrix
            prev_matrix.gl_code_status = 6 # Rejected by FC
            prev_matrix.save()
            print(f"Updated Previous Matrix {prev_matrix.id} to Rejected by FC")

    messages.success(
        request,
        f"GL Review submitted successfully for GL Code {gl_code}. Status updated to '{assignment.get_gl_code_status_display()}'."
    )

    if action == 'approve':
        # send mail to FC
        fc_email = dh.user.email
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
            f'Your GL Review for GL Code {gl_code} has been rejected by the Finance Controller.',
            settings.EMAIL_HOST_USER,
            [prev_reviewer.email],
            fail_silently=False,
        )

    return redirect("gl_reviews_page")


@login_required
@require_http_methods(["POST"])
def submit_gl_review_tower(request):
    """
    Submit a GL review for Tower Head (User Type 2).
    """
    try:
        assignment_id = request.POST.get("assignment_id")
        gl_code = request.POST.get("gl_code")
        action = request.POST.get("action")  # 'approve' or 'reject'

        assignment_ids = request.POST.getlist("assignment_ids[]")

        print("[1] Raw POST data")
        print("    action:", action)
        print("    assignment_id:", assignment_id)
        print("    assignment_ids:", assignment_ids)

        if not assignment_ids and assignment_id:
            assignment_ids = [assignment_id]
            print("[1.1] Single assignment fallback used")

        if not assignment_ids:
            print("[ERROR] No assignment IDs found")
            messages.error(request, "No GLs selected.")
            return redirect("gl_reviews_page")

        processed_count = 0

        for idx, a_id in enumerate(assignment_ids, start=1):
            print(f"[2.{idx}] Processing assignment_id:", a_id)

            try:
                assignment = ResponsibilityMatrix.objects.get(
                    id=a_id,
                    user=request.user
                )
            except ResponsibilityMatrix.DoesNotExist:
                print(f"[ERROR] Assignment not found or not owned by user: {a_id}")
                continue

            current_gl_code = assignment.gl_code
            print(f"[3.{idx}] GL Code:", current_gl_code)

            # Verify FC approval
            fc_assignment = ResponsibilityMatrix.objects.filter(
                gl_code=current_gl_code,
                user_role=3
            ).first()

            if not fc_assignment:
                print(f"[WARN] No FC assignment found for GL:", current_gl_code)
                continue

            print(f"[4.{idx}] FC status:", fc_assignment.gl_code_status)

            if fc_assignment.gl_code_status != 3:
                print(f"[SKIP] GL not approved by FC. Status:", fc_assignment.gl_code_status)
                continue

            trial_balance = TrialBalance.objects.filter(
                gl_code=current_gl_code
            ).first()

            if not trial_balance:
                print(f"[ERROR] No TrialBalance found for GL:", current_gl_code)
                continue

            print(f"[5.{idx}] TrialBalance ID:", trial_balance.id)

            gl_review = GLReview.objects.filter(
                trial_balance=trial_balance
            ).first()

            if not gl_review:
                print(f"[ERROR] No GLReview found for GL:", current_gl_code)
                continue

            print(f"[6.{idx}] GLReview ID:", gl_review.id)

            previous_trail = ReviewTrail.objects.filter(
                gl_review=gl_review
            ).order_by('-created_at').first()

            print(f"[7.{idx}] Previous trail ID:",
                  previous_trail.id if previous_trail else None)
            print(f"[8.{idx}] Performing action:", action)

            if action == 'approve':
                assignment.gl_code_status = 7
                fc_assignment.gl_code_status = 7
                fc_assignment.save()
                print(f"[9.{idx}] Tower Head APPROVED → status set to 7")

            elif action == 'reject':
                assignment.gl_code_status = 8
                fc_assignment.gl_code_status = 8
                fc_assignment.save()
                print(f"[9.{idx}] Tower Head REJECTED → FC status set to 8")

            else:
                print(f"[ERROR] Invalid action:", action)
                continue

            assignment.save()
            print(f"[10.{idx}] Assignment saved:", assignment.id)

            gl_review.reviewer = request.user
            gl_review.save()
            print(f"[11.{idx}] GLReview reviewer updated to Tower Head")

            ReviewTrail.objects.create(
                reviewer=request.user,
                reviewer_responsibility_matrix=assignment,
                gl_review=gl_review,
                previous_trail=previous_trail,
                reconciliation_notes=(
                    f"Bulk Action: {action.title()}"
                    if len(assignment_ids) > 1
                    else "Tower Head Review"
                ),
                gl_code=current_gl_code,
                action='Approved' if action == 'approve' else 'Rejected'
            )

            print(f"[12.{idx}] ReviewTrail created successfully")

            processed_count += 1

        print("Processed count:", processed_count)

        messages.success(
            request,
            f"Successfully processed {processed_count} GL reviews."
        )
        return redirect("gl_reviews_page")

    except Exception as e:
        print("[ERROR] submit_gl_review_tower crashed")
        print("Exception:", repr(e))
        import traceback
        traceback.print_exc()

        messages.error(request, "Something went wrong while processing GL reviews.")
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


@login_required
def review_trail_page(request):
    """
    Dedicated page for searching and viewing Review Trails.
    """
    gl_code = request.GET.get('gl_code', '').strip()
    context = {'gl_code': gl_code}
    
    # Get all unique GL codes for datalist
    # Combine ReviewTrail gl_codes and maybe existing GLs
    # For efficiency let's just grab from ReviewTrail and ResponsibilityMatrix
    gl_codes = set(ReviewTrail.objects.values_list('gl_code', flat=True).distinct())
    # You might want to add Assignment GLs too if they haven't started trailing yet, 
    # but the request implies showing trails.
    context['all_gl_codes'] = sorted([g for g in gl_codes if g])

    if gl_code:
        trails_qs = ReviewTrail.objects.filter(gl_code=gl_code).select_related('reviewer').order_by('created_at')
        
        # Get GL Name if possible
        # Try finding in TrialBalance or BalanceSheet or from the first trail
        gl_name = None
        first_trail = trails_qs.first()
        if first_trail and first_trail.gl_name:
            gl_name = first_trail.gl_name
        
        if not gl_name:
             # Fallback lookup
             bs = BalanceSheet.objects.filter(gl_acct=gl_code).first()
             if bs: gl_name = bs.gl_account_name

        context['gl_name'] = gl_name
        
        trails_data = []
        for trail in trails_qs:
            trails_data.append({
                'action': trail.action,
                'reviewer': f"{trail.reviewer.first_name} {trail.reviewer.last_name}" if trail.reviewer else "Unknown",
                'date': trail.created_at.strftime("%B %d, %Y"),
                'time': trail.created_at.strftime("%I:%M %p"),
                'notes': trail.reconciliation_notes
            })
        context['trails'] = trails_data
        
    return render(request, 'gl_reviews/review_trail_page.html', context)

