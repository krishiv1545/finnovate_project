import logging
from django.shortcuts import render
from django.http import StreamingHttpResponse, JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.shortcuts import redirect
import json
import os
import time
import re
from core_APP.models import Conversation, Message
import google.generativeai as genai


logger = logging.getLogger(__name__)


def dashboard_view(request):
    """Dashboard view."""

    if not request.user.is_authenticated:
        return redirect("landing_page")
    print("Dashboard view for User: ", request.user.id)
    if request.user.user_type == 1:
        # Admin
        return render(request, 'dashboard/dashboard.html')
    elif request.user.user_type in [2, 3]:
        # Tower Lead and Finance Controller
        return render(request, 'dashboard/dashboard.html')
    elif request.user.user_type == 4:
        # User
        return render(request, 'dashboard/dashboard.html')
    else:
        return render(request, 'dashboard/dashboard.html')


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
