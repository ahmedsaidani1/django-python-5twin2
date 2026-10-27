from django import forms


class StyledFormMixin:
    """Adds Bootstrap classes and HTML5 constraint attributes to every field,
    and links errors / help texts to their input with ``aria-describedby``."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(widget, forms.Select):
                css = "form-select"
            else:
                css = "form-control"
            widget.attrs.setdefault("class", css)
            if field.required and not isinstance(widget, forms.CheckboxInput):
                widget.attrs["required"] = True
            if field.help_text:
                widget.attrs["aria-describedby"] = f"id_{name}_help"

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name not in self.fields:
                continue
            attrs = self.fields[name].widget.attrs
            if "is-invalid" not in attrs.get("class", ""):
                attrs["class"] = f"{attrs.get('class', '')} is-invalid".strip()
            attrs["aria-invalid"] = "true"
            ids = [f"id_{name}_error"]
            if self.fields[name].help_text:
                ids.append(f"id_{name}_help")
            attrs["aria-describedby"] = " ".join(ids)


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs=attrs, format="%Y-%m-%d")
