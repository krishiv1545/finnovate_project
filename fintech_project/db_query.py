import os
import django
import sys

# Add project root to path
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from core_APP.models import TrialBalance, BalanceSheet, GLReview, ResponsibilityMatrix, ReviewTrail, Department, CustomUser
from django.db.models import Count, Sum

with open('db_analysis.txt', 'w', encoding='utf-8') as f:
    def log(msg):
        print(msg)
        f.write(msg + "\n")

    log("=" * 50)
    log("DATABASE ANALYSIS FOR DASHBOARD")
    log("=" * 50)

    user = CustomUser.objects.first()
    log(f"Using User: {user}")

    log("\n=== TrialBalance ===")
    count = TrialBalance.objects.count()
    log(f"Total Count: {count}")
    if count > 0:
        tb = TrialBalance.objects.first()
        log(f"Sample: gl_code='{tb.gl_code}', gl_name='{tb.gl_name}'")
        log(f"  amount={tb.amount} (Type: {type(tb.amount)})")
        log(f"  fs_main_head='{tb.fs_main_head}'")
        log(f"  fs_sub_head='{tb.fs_sub_head}'")
        log(f"  added_at={tb.added_at}")
        
        heads = list(TrialBalance.objects.values_list('fs_main_head', flat=True).distinct())
        log(f"Distinct fs_main_head: {heads}")
        
        # Check for empty dates
        no_date = TrialBalance.objects.filter(added_at__isnull=True).count()
        log(f"Records with no added_at: {no_date}")

    log("\n=== BalanceSheet ===")
    count = BalanceSheet.objects.count()
    log(f"Total Count: {count}")
    if count > 0:
        bs = BalanceSheet.objects.first()
        log(f"Sample: gl_acct='{bs.gl_acct}', variance_percent='{bs.variance_percent}'")
        
        # Check variance format
        variances = list(BalanceSheet.objects.values_list('variance_percent', flat=True).distinct()[:10])
        log(f"Sample variances: {variances}")

    log("\n=== GLReview ===")
    count = GLReview.objects.count()
    log(f"Total Count: {count}")
    if count > 0:
        statuses = GLReview.objects.values('status').annotate(count=Count('id'))
        log(f"Status distribution: {list(statuses)}")

    log("\n=== ResponsibilityMatrix ===")
    count = ResponsibilityMatrix.objects.count()
    log(f"Total Count: {count}")
    
    # Check Departments
    depts = list(ResponsibilityMatrix.objects.values_list('department__name', flat=True).distinct())
    log(f"Departments: {depts}")

    log("\n=== ReviewTrail ===")
    count = ReviewTrail.objects.count()
    log(f"Total Count: {count}")

