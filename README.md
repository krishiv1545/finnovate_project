# IIT-Gn Finnovate 2025 Hackathon

## 🤖 AI-Powered Financial Chatbot

This project features **Nirva AI**, a CPA-level accounting assistant with real-time AI capabilities via Google Gemini 2.0 and OpenAI.

## ⚡ Quick Start

### 1. Create Virtual Environment

From root (finnovate_project), run:

```bash
python -m venv env
env\Scripts\activate  # Windows
# or
source env/bin/activate  # Linux/Mac
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file parallel to `manage.py` with your API keys. See `ENV_SETUP.md` for details.

```bash
# Minimum required: At least ONE AI provider
OPENAI_API_KEY=sk-...
# OR
GOOGLE_AI_API_KEY=AIza...
```

### 4. Run Migrations

```bash
python fintech_project/manage.py makemigrations
python fintech_project/manage.py migrate
```

### 5. Create Superuser

```bash
python fintech_project/manage.py createsuperuser
```

### 6. Start Development Server

```bash
python fintech_project/manage.py runserver
```

### 7. Access Chatbot

Visit **http://localhost:8000/dashboard/** and start chatting!

## 📚 Documentation

- **SETUP.md** - Comprehensive setup guide
- **ENV_SETUP.md** - API key configuration
- **IMPLEMENTATION.md** - Technical details and migration notes

## ✨ Features

✅ **AI Streaming**: Real-time responses from Google Gemini or OpenAI  
✅ **CPA Expertise**: Specialized accounting knowledge  
✅ **Conversation History**: Persistent chat threads with sidebar navigation  
✅ **New Chat Button**: Start fresh conversations anytime  
✅ **Markdown Support**: Rich text rendering  
✅ **Smart Detection**: Balance sheet, GL, and TB query handling  
✅ **Progressively Enhanced**: Works with or without API keys
✅ **Responsive Design**: Works on desktop, tablet, and mobile

## 🎯 Try It Out

Ask Nirva anything:

- "Explain the accounting equation"
- "Convert this General Ledger to Trial Balance"
- "Show me GL variance analysis"
- "Validate my balance sheet"
