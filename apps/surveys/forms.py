"""Forms for creating surveys and uploading response files."""

from django import forms

from .models import Survey

# Refused before anything is read into memory. A survey export that exceeds
# this is almost certainly the wrong file.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = (".csv", ".xlsx", ".xls")


class SurveyForm(forms.ModelForm):
    """Create a survey to hold uploaded datasets."""

    class Meta:
        model = Survey
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(
                attrs={"autofocus": True, "placeholder": "Employee survey 2026"}
            ),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class DatasetUploadForm(forms.Form):
    """Accept a response export.

    Size and extension are checked here, before the file reaches the parser,
    so an obviously wrong upload fails fast with a message the user can act on.
    """

    file = forms.FileField(
        label="Response file",
        help_text="CSV or Excel, one row per respondent and one column per question.",
    )

    def clean_file(self) -> object:
        uploaded = self.cleaned_data["file"]

        if not uploaded.name.lower().endswith(ALLOWED_EXTENSIONS):
            raise forms.ValidationError("Upload a .csv, .xlsx or .xls file.")

        if uploaded.size > MAX_UPLOAD_BYTES:
            limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
            raise forms.ValidationError(f"That file is larger than {limit_mb} MB.")

        return uploaded
