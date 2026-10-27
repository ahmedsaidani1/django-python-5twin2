from django import forms

from apps.core.forms import StyledFormMixin

from .models import Message


class MessageForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Message
        fields = ("body",)
        widgets = {"body": forms.Textarea(attrs={"rows": 2, "maxlength": 2000, "placeholder": "Votre message…"})}

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError("Le message ne peut pas être vide.")
        return body
