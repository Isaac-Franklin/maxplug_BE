import json
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
# Create your models here.
from django.conf import settings


class UserDetails(models.Model):
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    fullname = models.CharField(max_length= 3000, null=True, blank = True)
    emailAddress = models.EmailField(max_length= 300, null=True, blank = True)
    phoneNumber = models.IntegerField(default=0)
    referrerCode = models.CharField(max_length= 3000, null=True, blank = True)
    password = models.CharField(max_length= 3000, null=True, blank = True)
    verificationStatus = models.BooleanField(default = False)
    profileImage = models.ImageField(upload_to='userProfileImages/', )
    # 
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-edited_at', '-created_at']
        
    def __str__(self):
        return f'UserEmail{self.emailAddress}. fullname: {self.fullname}'
        



class UserKYCDetails(models.Model):
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    emailAddress = models.EmailField(max_length=300, null=True, blank=True)
    homeaddress = models.CharField(max_length=3000, null=True, blank=True)
    birth_date = models.CharField(max_length=3000, null=True, blank=True)
    NIN = models.CharField(max_length=3000, null=True, blank=True)
    BVN = models.CharField(max_length=3000, null=True, blank=True)
    idcard = models.ImageField(upload_to='userifcardsimages/', null=True, blank=True)
    utilitybillimage = models.ImageField(upload_to='utilitybillimages/', null=True, blank=True)
    passportphotograph = models.ImageField(upload_to='passportphotographimages/', null=True, blank=True)
    # 
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-edited_at', '-created_at']
        
    def __str__(self):
        return f'UserEmail{self.user.email}'
    
    @property
    def is_kyc_fully_submitted(self) -> bool:
        """
        Checks if all mandatory fields (homeaddress, birth_date, NIN, BVN)
        have been filled.
        """
        
        # Check only the specific required fields
        required_fields_present = all([
            self.homeaddress,
            self.birth_date, 
            self.NIN,        
            self.BVN,        
        ])
        
        return required_fields_present

    
    
class UserAccountDetails(models.Model):
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    accountName = models.CharField(max_length= 3000, null=True, blank = True)
    bankName = models.CharField(max_length= 3000, null=True, blank = True)
    accountNumber = models.CharField(max_length= 3000, null=True, blank = True)
    # 
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-edited_at', '-created_at']
        
    def __str__(self):
        return f'UserEmail{self.accountName}. fullname: {self.bankName}'
        
        

# --- Shared Choices for Status Fields ---
STATUS_PENDING = 'PENDING'
STATUS_RESOLVED = 'RESOLVED'
STATUS_AWAITING_INFO = 'AWAITING_INFO'

STATUS_CHOICES = [
    (STATUS_PENDING, 'Pending Review'),
    (STATUS_RESOLVED, 'Resolved'),
    (STATUS_AWAITING_INFO, 'Awaiting User Information'),
]


# --- Base Model for Submission Tracking ---
class SubmissionBase(models.Model):
    """Abstract base class to inherit common fields for all user submissions."""
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        help_text="The user who submitted this issue."
    )
    issue_description = models.TextField(
        help_text="Detailed description of the problem."
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text="Current status of the issue."
    )
    admin_response = models.TextField(
        null=True, 
        blank=True, 
        help_text="Response provided by the admin team."
    )
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']



# --- 1. Fix Funding Issue Model ---
class FixFundingIssue(SubmissionBase):
    """Model for issues related to deposits not reflecting (Funding Issues)."""
    deposit_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        null=True,
        help_text="The amount that was deposited."
    )
    reference_id = models.CharField(
        max_length=100,
        help_text="Bank/Payment Gateway Transaction ID or Reference."
    )
    proof_of_payment = models.TextField(
        null=True, 
        blank=True, 
        help_text="Link or description of proof of payment (e.g., screenshot link)."
    )

    def __str__(self):
        return f'Funding Issue: {self.reference_id} ({self.status})'

# --- 2. Undelivered Transaction Model ---
class UndeliveredTransaction(SubmissionBase):
    """Model for issues related to failed/undelivered services (Airtime, Data, Bills)."""
    transaction_type = models.CharField(
        max_length=50,
        help_text="Type of transaction (e.g., 'Airtime', 'Data', 'Electricity')."
    )
    recipient_details = models.CharField(
        max_length=100,
        help_text="Recipient phone number, meter number, or cable TV ID."
    )
    transaction_id = models.CharField(
        max_length=100,
        help_text="Internal transaction ID from your application."
    )

    amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        null=True,
        help_text="The amount in question."
    )

    def __str__(self):
        return f'Undelivered Txn: {self.transaction_id} ({self.status})'

# --- 3. Card Related Issue Model ---
class CardRelatedIssue(SubmissionBase):
    """Model for issues related to user payment cards."""
    CARD_CATEGORIES = [
        ('Lost or Stolen Card', 'Lost or Stolen Card'),
        ('Activation/Deactivation Issue', 'Activation/Deactivation Issue'),
        ('Card Transaction Failed', 'Card Transaction Failed'),
        ('Other Card Issue', 'Other Card Issue'),
    ]

    issue_category = models.CharField(
        max_length=50,
        choices=CARD_CATEGORIES,
        help_text="Specific category of the card issue."
    )
    card_reference = models.CharField(
        max_length=100,
        null=True, 
        blank=True, 
        help_text="Reference/Masked ID of the card involved."
    )
    issue_description = models.CharField(
        max_length=300,
        null=True, 
        blank=True, 
        help_text="Issue description"
    )

    def __str__(self):
        return f'Card Issue: {self.issue_category} ({self.status})'

# --- 4. FAQ Entry Model (Content, not Submission) ---
class FAQEntry(models.Model):
    """Model for static Frequently Asked Questions content."""
    CATEGORY_CHOICES = [
        ('FUNDING', 'Funding'),
        ('TRANSACTIONS', 'Transactions'),
        ('CARDS', 'Cards'),
        ('GENERAL', 'General'),
    ]

    question = models.CharField(max_length=255)
    answer = models.TextField()
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    order = models.IntegerField(default=0, help_text="Order in which the FAQ should be displayed.")
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'category']
        verbose_name = "FAQ Entry"
        verbose_name_plural = "FAQ Entries"
    
    def __str__(self):
        return self.question



# --- UTILITY FUNCTION FOR HISTORY RETRIEVAL ---

def get_selfcare_history(user):
    """
    Fetches, unifies, and sorts all support submissions for a given user.

    Args:
        user (User): The authenticated Django User object.

    Returns:
        list: A list of dictionaries, sorted by 'created_at' (newest first),
              containing a unified view of all user submissions.
    """
    if not user.is_authenticated:
        return []

    # 1. Fetch data from all three submission models for the specific user
    funding_issues = FixFundingIssue.objects.filter(user=user)
    transaction_issues = UndeliveredTransaction.objects.filter(user=user)
    card_issues = CardRelatedIssue.objects.filter(user=user)

    unified_history = []

    # 2. Process Funding Issues
    for issue in funding_issues:
        unified_history.append({
            'id': issue.id,
            'issue_type': 'Fix Funding Issue',
            'summary': f"Ref: {issue.reference_id}",
            'issue_description': issue.issue_description,
            'status': issue.status,
            'admin_response': issue.admin_response,
            'created_at': issue.created_at,
        })

    # 3. Process Undelivered Transaction Issues
    for issue in transaction_issues:
        # Get the friendly display name for the transaction type, if needed
        # Fallback to the stored value if no display name is defined/needed
        issue_type_display = f"Undelivered {issue.transaction_type}" 
        
        unified_history.append({
            'id': issue.id,
            'issue_type': issue_type_display,
            'summary': f"Txn ID: {issue.transaction_id}",
            'issue_description': issue.issue_description,
            'status': issue.status,
            'admin_response': issue.admin_response,
            'created_at': issue.created_at,
        })

    # 4. Process Card Related Issues
    for issue in card_issues:
        # Get the friendly display name for the issue category
        category_display = dict(CardRelatedIssue.CARD_CATEGORIES).get(issue.issue_category, 'Unknown Card Issue')
        
        unified_history.append({
            'id': issue.id,
            'issue_type': 'Card Related Issue',
            'summary': f"{category_display} (Ref: {issue.card_reference or 'N/A'})",
            'issue_description': issue.issue_description,
            'status': issue.status,
            'admin_response': issue.admin_response,
            'created_at': issue.created_at,
        })

    # 5. Sort the combined list by 'created_at' (newest first)
    print('unified_history')
    print(unified_history)
    unified_history.sort(key=lambda x: x['created_at'], reverse=True)

    return unified_history

class AccountDeletionRequest(models.Model):
    """
    Stores a formal request from a user to have their account deleted.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='deletion_request',
        verbose_name='User Requesting Deletion'
    )
    primary_reason = models.CharField(max_length=255)
    detailed_feedback = models.TextField(blank=True, null=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    is_processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Account Deletion Request"
        verbose_name_plural = "Account Deletion Requests"
        # Only one active request per user should exist, enforced in the view
        constraints = [
            models.UniqueConstraint(fields=['user'], condition=models.Q(is_processed=False), name='unique_unprocessed_request')
        ]
        ordering = ['-requested_at']

    def __str__(self):
        return f"Deletion Request for {self.user.email} - Status: {'Processed' if self.is_processed else 'Pending'}"




class SaveUserFCMToken(models.Model):
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    fcmtoken = models.CharField(max_length= 3000, null=True, blank = True)
    # 
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-edited_at', '-created_at']
        
    def __str__(self):
        return f'UserEmail{self.fcmtoken}'
        
        
class UserVirtualAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    va_number = models.CharField(max_length=20, unique=True)  # PalmPay VA number
    status = models.CharField(max_length=20, default="ACTIVE")  # ACTIVE, INACTIVE
    created_at = models.DateTimeField(auto_now_add=True)
    notify_url = models.URLField(null=True, blank=True)


class UserAccountBalance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    virtual_account = models.ForeignKey(UserVirtualAccount, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pending_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_updated = models.DateTimeField(auto_now=True)


class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('DEPOSIT', 'Deposit'),
        ('TRANSFER', 'Transfer'),
        ('WITHDRAWAL', 'Withdrawal')
    ]
    TRANSACTION_STATUS = [
        ('PENDING', 'Pending'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed')
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    virtual_account = models.ForeignKey(UserVirtualAccount, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    reference = models.CharField(max_length=50, unique=True)  # Unique transaction ID
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='PENDING')
    metadata = models.JSONField(blank=True, null=True)  # Store extra info
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=100, null=True, blank=True)


class WebhookLog(models.Model):
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)


