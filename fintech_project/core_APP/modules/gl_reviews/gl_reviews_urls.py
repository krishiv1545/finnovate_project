from django.urls import path
from .gl_reviews import (
    gl_reviews_view, 
    balance_sheet_view, 
    upload_gl_supporting_document, 
    submit_gl_review_preparer, 
    submit_gl_review_reviewer,
    remove_gl_supporting_document,
    get_review_trail,
    review_trail_page,
    submit_gl_review_bufc
)


urlpatterns = [
    path('', gl_reviews_view, name='gl_reviews_page'),
    path('remove_gl_supporting_document/<str:document_id>', remove_gl_supporting_document, name='remove_gl_supporting_document'),
    path('tier3/', balance_sheet_view, name='reports_tier3'),
    path('upload-document/', upload_gl_supporting_document, name='upload_gl_supporting_document'),
    path('submit-review/', submit_gl_review_preparer, name='submit_gl_review_preparer'),
    path('submit-review/reviewer/', submit_gl_review_reviewer, name='submit_gl_review_reviewer'),
    path('submit-review/bufc/', submit_gl_review_bufc, name='submit_gl_review_bufc'),
    path('trail/<str:gl_code>/', get_review_trail, name='get_review_trail'),
    path('trail-search/', review_trail_page, name='review_trail_page'),
]

