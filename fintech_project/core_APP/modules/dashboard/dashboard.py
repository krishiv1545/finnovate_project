import logging
from django.shortcuts import render
from django.http import StreamingHttpResponse, JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.shortcuts import redirect
from django.db.models import Sum, Count, Q, F, Case, When, Value, FloatField
from django.db.models.functions import TruncMonth, TruncQuarter, Coalesce
from django.utils import timezone
import json
import os
import time
import re
import datetime
from core_APP.models import (
    Conversation, Message, TrialBalance, BalanceSheet, 
    GLReview, ResponsibilityMatrix, ReviewTrail, Department, CustomUser
)
import google.generativeai as genai


logger = logging.getLogger(__name__)


class DashboardAnalytics:
    @staticmethod
    def get_dashboard_data(user):
        """Aggregate data for all 4 rows of the dashboard."""
        return {
            "financials": DashboardAnalytics.get_financial_health(user),
            "operations": DashboardAnalytics.get_operational_efficiency(user),
            "profitability": DashboardAnalytics.get_pl_profitability(user),
            "compliance": DashboardAnalytics.get_risk_compliance(user),
        }

    @staticmethod
    def get_financial_health(user):
        # 1. GL Variance Trends (Line)
        end_date = timezone.now()
        start_date = end_date - datetime.timedelta(days=365)
        
        monthly_variance = TrialBalance.objects.filter(
            user=user, 
            added_at__range=(start_date, end_date)
        ).annotate(
            month=TruncMonth('added_at')
        ).values('month').annotate(
            net_amount=Sum('amount')
        ).order_by('month')

        # 2. Assets vs Liabilities (Bar) - Quarterly
        # Aggregate specific heads
        # Map DB values to Logic values
        asset_heads = ['Assets', 'Current Assets', 'Non-Current Assets']
        liab_heads = ['Liabilities', 'Current Liabilities', 'Non-Current Liabilities']
        
        quarterly_pos = TrialBalance.objects.filter(
            user=user,
            fs_main_head__in=asset_heads + liab_heads
        ).annotate(
            quarter=TruncQuarter('added_at')
        ).values('quarter', 'fs_main_head').annotate(
            total=Sum('amount')
        ).order_by('quarter')
        
        # 3. Balance Sheet Mix (Doughnut)
        bs_mix = TrialBalance.objects.filter(
            user=user,
            fs_main_head__in=asset_heads + liab_heads + ['Equity']
        ).values('fs_main_head').annotate(
            total=Sum('amount')
        )
        
        return {
            "gl_variance": list(monthly_variance),
            "quarterly_position": list(quarterly_pos),
            "bs_mix": list(bs_mix),
        }

    @staticmethod
    def get_operational_efficiency(user):
        # 5. Review Status Breakdown (Pie)
        status_counts = GLReview.objects.filter(
            trial_balance__user=user
        ).values('status').annotate(count=Count('id'))
        
        # 6. Department Workload (Bar)
        dept_workload = ResponsibilityMatrix.objects.values(
            'department__name'
        ).annotate(count=Count('id')).order_by('-count')[:10]
        
        # 7. My Pending Reviews (Gauge)
        my_pending = GLReview.objects.filter(
            reviewer=user,
            status=1 # Pending
        ).count()
        
        # 8. Review Activity Timeline (Line)
        activity = ReviewTrail.objects.annotate(
            day=TruncMonth('created_at')
        ).values('day').annotate(count=Count('id')).order_by('day')
        
        return {
            "review_status": list(status_counts),
            "dept_workload": list(dept_workload),
            "my_pending": my_pending,
            "activity_timeline": list(activity)
        }
    
    @staticmethod
    def get_pl_profitability(user):
        # 9. Revenue vs Expenses (Bar)
        rev_exp = TrialBalance.objects.filter(
            user=user,
            fs_main_head__in=['Revenue', 'Income', 'Expenses', 'Tax Expense']
        ).values('fs_main_head').annotate(total=Sum('amount'))
        
        # 10. Expense Composition (Polar Area)
        # Using fs_main_head filter for 'Expenses' or related
        exp_comp = TrialBalance.objects.filter(
            user=user,
            fs_main_head__in=['Expenses', 'Tax Expense']
        ).values('fs_sub_head').annotate(total=Sum('amount')).order_by('-total')[:8]
        
        # 11. Top Revenue Streams
        top_rev = TrialBalance.objects.filter(
            user=user,
            fs_main_head__in=['Revenue', 'Income']
        ).values('gl_name').annotate(total=Sum('amount')).order_by('-total')[:5]
        
        return {
            "rev_vs_exp": list(rev_exp),
            "expense_composition": list(exp_comp),
            "top_revenue": list(top_rev)
        }

    @staticmethod
    def get_risk_compliance(user):
        # 13. Top Account Variances
        # BalanceSheet has variance_percent as CharField (e.g. "5.2%", "Not Applicable", "Red")
        # We fetch all and filter/clean in python to avoid complex regex logic in SQL for sqlite/other DBs
        raw_bs = BalanceSheet.objects.exclude(variance_percent__isnull=True).values('gl_account_name', 'variance_percent', 'variance_percent')[:100]
        
        # Clean data in Python
        cleaned_bs = []
        for item in raw_bs:
            v_str = str(item['variance_percent']).replace('%', '').strip()
            try:
                val = float(v_str)
                item['variance_val'] = val
                cleaned_bs.append(item)
            except ValueError:
                continue
                
        # Sort by absolute variance
        cleaned_bs.sort(key=lambda x: abs(x['variance_val']), reverse=True)
        top_variances = cleaned_bs[:6]
        
        # 14. Reconciliation Progress
        total_recon = BalanceSheet.objects.count()
        completed_recon = BalanceSheet.objects.filter(recon_status__icontains='Completed').count()
        
        # 15. Top Rejected Accounts
        rejected = ReviewTrail.objects.filter(
            action='Rejected'
        ).values('gl_name').annotate(count=Count('id')).order_by('-count')[:5]
        
        # 16. Documentation Hygiene
        total_reviews = GLReview.objects.filter(trial_balance__user=user).count()
        reviews_with_docs = GLReview.objects.filter(
            trial_balance__user=user,
            supporting_documents__isnull=False
        ).distinct().count()
        
        return {
            "top_variances": top_variances, 
            "recon_progress": {"total": total_recon, "completed": completed_recon},
            "top_rejected": list(rejected),
            "doc_hygiene": {"total": total_reviews, "with_docs": reviews_with_docs}
        }


def dashboard_view(request):
    """Dashboard view with dynamic analytics."""

    if not request.user.is_authenticated:
        return redirect("landing_page")
    
    print("Dashboard view for User: ", request.user.id)
    
    context = {}
    try:
        # Fetch dynamic data
        data = DashboardAnalytics.get_dashboard_data(request.user)
        print(f"Dashboard data: {data}")
        logger.info(f"Dashboard data: {data}")
        context['dashboard_data'] = data # Passed as dict, template can use json_script
    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        context['dashboard_data'] = {}

    return render(request, 'dashboard/dashboard.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def chat_stream(request):
    """
    Enhanced streaming chat endpoint with MCP support, Gemini integration,
    and accounting-specific features.
    """
    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
        messages_list = payload.get('messages') or []
    except json.JSONDecodeError:
        return HttpResponseBadRequest('Invalid JSON')

    # Auth check
    if not request.user or not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized - Please sign in'}, status=401)

    # Get conversation
    conversation_id = payload.get('conversationId')
    conversation_obj = None
    if conversation_id:
        try:
            conversation_obj = Conversation.objects.get(id=conversation_id, user=request.user)
        except Conversation.DoesNotExist:
            return JsonResponse({'error': 'Conversation not found'}, status=404)

    # Extract user message
    user_content = ''
    for msg in reversed(messages_list):
        if (msg.get('role') or '').lower() == 'user':
            user_content = msg.get('content') or ''
            break

    # Create conversation if first message
    is_first_message = not conversation_obj
    if is_first_message:
        title = generate_conversation_title(user_content)
        conversation_obj = Conversation.objects.create(user=request.user, title=title)

    # Save user message
    Message.objects.create(
        conversation=conversation_obj,
        user=request.user,
        content=user_content,
        role='user',
    )

    # Prepare system prompt
    system_prompt = """
    **ACCOUNTING & FINANCIAL EXPERTISE MODE ACTIVATED**

    You are now operating with specialized accounting knowledge. Follow these CRITICAL rules:

    **FUNDAMENTAL ACCOUNTING PRINCIPLES:**

    - **The Accounting Equation**: Assets = Liabilities + Equity (ALWAYS verify this holds)
    - **Debit/Credit Rules**: 
    • Assets & Expenses: Debit increases, Credit decreases
    • Liabilities, Equity & Revenue: Credit increases, Debit decreases
    - **Trial Balance Rule**: Total Debits MUST equal Total Credits (sum = 0)

    **GENERAL LEDGER TO TRIAL BALANCE CONVERSION PROTOCOL:**

    1. **NEVER ASSUME DATA STRUCTURE** - Always examine and confirm:
    - Column names and their meaning
    - Date ranges and accounting periods
    - Currency and number formats
    - Account coding system used

    2. **VALIDATION REQUIREMENTS**:
    - Verify GL data completeness before processing
    - Check for duplicate entries or missing transactions
    - Ensure account codes match standard chart of accounts
    - Validate that all entries have both debit and credit components

    3. **CALCULATION METHODOLOGY**:
    - Group transactions by account code/name
    - Sum debits and credits separately for each account
    - Calculate net balance (debit - credit) for each account
    - MANDATORY: Verify total debits = total credits
    - Flag any accounts with unusual balances

    **WHEN PROCESSING FINANCIAL DATA**:
    - State your understanding of the data structure BEFORE processing
    - Show sample calculations for verification
    - Highlight any accounts that don't follow normal balance patterns
    - Provide detailed reconciliation between source GL and final TB

    **Response Formatting Guidelines:**
    - Always format your responses using Markdown syntax
    - Use **bold** for emphasis and important points
    - Use bullet points and numbered lists for clarity
    - Format links as [text](url)
    - Use code blocks with ``` for code snippets
    - Use inline code with ` for commands, file names, and technical terms
    - Use headings (##, ###) to organize longer responses
    - Make your responses clear, concise, and well-structured

    **Tool Execution Guidelines:**
    - Explain what you're doing before using tools
    - Provide clear feedback about the results
    - Include relevant links when appropriate
    """

    # Generate AI response
    accumulated = []
    
    def generate_stream():
        # Try to use Google Gemini if key is available
        if settings.GOOGLE_AI_API_KEY:
            yield from stream_google_gemini(messages_list, system_prompt)

    def yielding_and_persist():
        for chunk in generate_stream():
            accumulated.append(chunk)
            yield chunk
        
        # Save assistant message after streaming completes
        assistant_text = ''.join(accumulated)
        if assistant_text:
            Message.objects.create(
                conversation=conversation_obj,
                user=request.user,
                content=assistant_text,
                role='assistant',
            )

    response = StreamingHttpResponse(yielding_and_persist(), content_type='text/plain; charset=utf-8')
    response['X-Conversation-Id'] = str(conversation_obj.id)
    return response


def stream_google_gemini(messages_list, system_prompt):
    """
    Stream response from Google Gemini 2.5 Pro.
    """
    try:        
        genai.configure(api_key=settings.GOOGLE_AI_API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Prepare messages with system prompt
        gemini_messages = [{'role': 'user', 'parts': [system_prompt]}]
        for msg in messages_list:
            gemini_messages.append({
                'role': msg.get('role', 'user'),
                'parts': [msg.get('content', '')]
            })
        
        # Configure generation
        temperature = 0.1
        
        # Generate stream
        response = model.generate_content(
            gemini_messages,
            stream=True,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=8192,
            )
        )
        
        for chunk in response:
            if chunk.text:
                yield chunk.text
                
    except Exception as e:
        logger.error(f'Google Gemini streaming error: {str(e)}')
        yield f"\n\n*Error: Could not stream from Google Gemini. {str(e)}*"


def generate_conversation_title(first_message: str) -> str:
    """
    Generate a conversation title from the first message.
    """
    clean = (first_message or '').replace('\n', ' ').strip()
    if len(clean) <= 50:
        return clean or 'New conversation'
    words = clean.split(' ')
    title = ''
    for w in words:
        if len(title) + len(w) + (1 if title else 0) <= 47:
            title += ((' ' if title else '') + w)
        else:
            break
    return (title or clean[:47]) + '...'


@login_required
def list_conversations(request):
    """
    List all conversations for the authenticated user.
    """
    data = [
        {
            'id': str(c.id),
            'title': c.title,
            'created_at': c.created_at.isoformat(),
            'updated_at': c.updated_at.isoformat(),
        }
        for c in Conversation.objects.filter(user=request.user).order_by('-updated_at')
    ]
    return JsonResponse({'conversations': data})


@login_required
def list_messages(request, conv_id: str):
    """
    List all messages in a conversation.
    """
    try:
        conv = Conversation.objects.get(id=conv_id, user=request.user)
    except Conversation.DoesNotExist:
        return JsonResponse({'error': 'Conversation not found'}, status=404)
    
    msgs = [
        {
            'id': str(m.id),
            'conversation_id': str(conv.id),
            'content': m.content,
            'role': m.role,
            'created_at': m.created_at.isoformat(),
        }
        for m in conv.messages.all().order_by('created_at')
    ]
    return JsonResponse({'messages': msgs})
