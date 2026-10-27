from django import forms

from apps.core.forms import StyledFormMixin

from .models import Review


class ReviewForm(StyledFormMixin, forms.ModelForm):
    rating = forms.TypedChoiceField(
        label="Note", coerce=int, choices=[(i, f"{i} / 5") for i in range(5, 0, -1)], widget=forms.RadioSelect
    )

    class Meta:
        model = Review
        fields = ("rating", "comment")
        widgets = {"comment": forms.Textarea(attrs={"rows": 4, "maxlength": 1500, "minlength": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rating"].widget.attrs = {"class": "form-check-input"}

    def clean_comment(self):
        comment = self.cleaned_data["comment"].strip()
        if len(comment) < 5:
            raise forms.ValidationError("Le commentaire doit contenir au moins 5 caractères.")
        return comment
