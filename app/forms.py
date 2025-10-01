# app/forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm
from django.contrib.auth import get_user_model
from .models import UserProfile

User = get_user_model()


from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["username"].label = "Email"
        self.fields["username"].widget.attrs.update(
            {
                "class": "w-full px-4 py-2.5 bg-slate-50 border border-slate-300 rounded-lg placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow",
                "placeholder": "Enter your email",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "class": "w-full px-4 py-2.5 bg-slate-50 border border-slate-300 rounded-lg placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow",
                "placeholder": "••••••••",
            }
        )


from django import forms
from django.contrib.auth.forms import BaseUserCreationForm
from .models import User, UserProfile

INPUT_CLASSES = (
    "mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm "
    "placeholder-gray-400 focus:outline-none focus:ring-blue-primary "
    "focus:border-blue-primary sm:text-sm"
)
TEXTAREA_CLASSES = f"{INPUT_CLASSES} resize-y"


class UserRegistrationForm(BaseUserCreationForm):
    """
    Handles new user creation with a cleaner, more maintainable approach.
    """

    email = forms.EmailField(
        required=True, help_text="A valid email address is required."
    )
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field.label:
                placeholder_text = f"Enter your {field.label.lower()}..."
            else:
                placeholder_text = f"Enter {field_name.replace('_', ' ')}..."

            field.widget.attrs.update(
                {"class": INPUT_CLASSES, "placeholder": placeholder_text}
            )

    # ✅ YEH HISSA BADLA GAYA HAI
    def save(self, commit=True):
        # Pehle user object banao, lekin database mein save mat karo.
        user = super().save(commit=False)
        # User ke username ko uske email ke barabar set karo.
        user.username = self.cleaned_data["email"]
        if commit:
            # Ab user ko database mein save karo.
            user.save()
        return user

    class Meta(BaseUserCreationForm.Meta):
        model = User
        # Yahan 'username' add karne ki zaroorat nahi hai,
        # kyunki hum use save() method mein handle kar rahe hain.
        fields = ("email", "first_name", "last_name")


class UserProfileRegistrationForm(forms.ModelForm):
    """
    Handles the user profile fields with the same consistent styling.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field.label:
                placeholder_text = f"Enter your {field.label.lower()}..."
            else:
                placeholder_text = f"Enter {field_name.replace('_', ' ')}..."

            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update(
                    {
                        "class": TEXTAREA_CLASSES,
                        "rows": "1",
                        "placeholder": placeholder_text,
                    }
                )
            else:
                field.widget.attrs.update(
                    {"class": INPUT_CLASSES, "placeholder": placeholder_text}
                )

    class Meta:
        model = UserProfile
        fields = ("phone_number", "address")
