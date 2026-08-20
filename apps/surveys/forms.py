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


class StartRecordForm(forms.ModelForm):
    """Name a record and give it its responses in one step.

    These used to be two screens: create an empty survey, then find it again
    and upload to it. Nothing happens in between — the survey has no meaning
    until it holds data — so the split cost the user a screen and taught them
    a container concept before it could pay off.
    """

    file = forms.FileField(
        label="Response file",
        help_text="CSV or Excel. One row per respondent, one column per question.",
    )

    class Meta:
        model = Survey
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(
                attrs={"autofocus": True, "placeholder": "Employee survey 2026"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Optional. What this survey asked, and of whom."}
            ),
        }

    def clean_file(self) -> object:
        return _validate_upload(self.cleaned_data["file"])


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
        return _validate_upload(self.cleaned_data["file"])


def _validate_upload(uploaded: object) -> object:
    """Reject an obviously wrong file before the parser ever reads it.

    Shared by both upload paths so a file refused on one screen is refused
    identically on the other.
    """
    if not uploaded.name.lower().endswith(ALLOWED_EXTENSIONS):
        raise forms.ValidationError("Upload a .csv, .xlsx or .xls file.")

    if uploaded.size > MAX_UPLOAD_BYTES:
        limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise forms.ValidationError(f"That file is larger than {limit_mb} MB.")

    return uploaded
