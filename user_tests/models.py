# user_tests/models.py

from django.db import models
from django.utils import timezone

# IMPORTANT: QuestionPaper model purani 'app' mein hai.
# Humein use yahan import karna hoga.
# Agar aapne QuestionPaper ko 'app' se 'core' app mein move kiya hai toh path badal dena.
from app.models import QuestionPaper


# ----------------------------------------------------------------------
# --- MODEL FOR CANDIDATE REGISTRATION AND REPETITION CHECK ---
# ----------------------------------------------------------------------

class TestRegistration(models.Model):
    """
    Stores one unique attempt (registration) by an email for a specific Question Paper.
    This model has been MOVED from the 'app' module.
    """
    name = models.CharField(max_length=255)

    # Email is NOT unique across the whole table.
    email = models.EmailField(max_length=255)

    phone_number = models.CharField(max_length=15, null=True, blank=True)
    address = models.TextField(null=True, blank=True)

    # Link to the test paper (QuestionPaper model se Foreign Key)
    question_paper = models.ForeignKey(
        QuestionPaper,
        on_delete=models.CASCADE,
        related_name="registrations"
    )

    start_time = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=False)

    class Meta:
        # **CORE CONSTRAINT:** Ensures same email cannot be used for the same paper twice.
        unique_together = ('email', 'question_paper')

    def __str__(self):
        return f"{self.email} registered for {self.question_paper.title}"

# Note: Aage aapko ismein TestAttempt aur UserAnswer jaise models bhi banane chahiye.